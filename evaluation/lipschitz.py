import numpy as np
import torch
from torch_geometric.data import Data
from util import random_derangement

def local_lipschitz_bounds(perturbations):
    """ Function that calculates local Lipschitz bounds given some random perturbations. 
    
    Parameters:
    -----------
    perturbations : dict
        Mapping from perturbation_magnitude -> tensor of output perturbations.

    Returns:
    --------
    slope_mean : float
        The slope of the linear function fit to mean perturbations.
    slope_median : float
        The slope of the linear function fit to median perturbations.
    slope_max : float
        The slope of the linear function that upper bounds all perturbations. This is an empirical (tight) bound on the local Lipschitz constant.
    slope_min : float
        The slope of the linear function that lower bounds all perturbations.
    """ 
    xs = torch.tensor(list(perturbations.keys())).numpy()
    ys = torch.stack(list(perturbations.values()))
    means, meds, maxs, mins = ys.mean(dim=-1), ys.median(dim=-1)[0].numpy(), ys.max(axis=-1)[0].numpy(), ys.min(axis=-1)[0].numpy()

    return (means / xs).mean(), (meds / xs).mean(), (maxs / xs).max(), (mins / xs).min()


@torch.no_grad()
def logit_space_bounds(model, dataset):
    """ Gets bounds for the logit space in each dimension given a certain dataset. 
    
    Parameters:
    -----------
    model : torch.nn.Module
        A torch model.
    dataset : torch_geometric.data.Dataset
        A dataset.
    
    Returns:
    --------
    min : torch.tensor, shape [num_classes]
        Minimal values in logit space.
    max : torch.tensor, shape [num_classes]
        Maximal values in logit space
    """
    logits = model(dataset)[-1][dataset.mask]
    mins, maxs = logits.min(dim=0)[0], logits.max(dim=0)[0]
    for idx in range(1, len(dataset)):
        logits = model(dataset[idx])[-1][dataset[idx].mask]
        mins = torch.min(mins, logits.min(dim=0)[0])
        maxs = torch.max(maxs, logits.max(dim=0)[0])
    return mins, maxs


@torch.no_grad()
def local_perturbations(model, dataset, perturbations=np.linspace(0.1, 5.0, 50), num_perturbations_per_sample=10, seed=None):
    """ Locally perturbs data and see how much the logits are perturbed. 
    
    Parameters:
    -----------
    model : torch.nn.Module
        The model to check
    dataset : torch_geometric.data.Dataset
        The dataset to investigate. Currently, only dataset is used.
    perturbations : iterable
        Different magnitudes of noise to check.
    num_perturbations_per_sample : int
        How many random perturbations to use per sample and per noise magnitude.
    seed : int or None
        If given, seeds the rng and makes the perturbations deterministic.
    
    Returns:
    --------
    perturbations : dict
        Mapping from input_perturbations -> `num_nodes * num_perturbations_per_sample` output perturbations.
    """
    if seed is not None:
        torch.manual_seed(seed)
    logits = model(dataset)[-1]
    logits = logits[dataset.mask]
    result = {}
    for eps in perturbations:
        results_eps = []
        for _ in range(num_perturbations_per_sample):
            noise = torch.randn(list(dataset.x[dataset.mask].size()), device=dataset.x.device)
            noise = noise / noise.norm(dim=-1, keepdim=True) * eps
            x_perturbed = dataset.x
            x_perturbed[dataset.mask] += noise
            data = Data(x=x_perturbed, edge_index=dataset.edge_index)
            logits_perturbed = model(data)[-1][dataset.mask]
            results_eps.append((logits - logits_perturbed).norm(dim=1).detach().cpu())
            
        result[eps] = torch.cat(results_eps)
    return result


def permute_features(x, num_permutations, per_sample=True, rng=None):
    """ Randomly permutes the features of a 2d tensor. 
    
    Parameters:
    -----------
    torch.Tensor, shape [N, D]
        The tensor to permute.
    num_permutations : int
        How many elements will be permuted.
    per_sample : bool
        If `True`, then the columns to be permuted are re-rolled for each row.
        If `False`, then the columns to be permuted are globally selected for all rows.
    rng : np.random.RandomState or None
        The rng to use.
    """
    if rng is None:
        rng = np.random.RandomState(np.random.randint(1 << 32))
    per_sample = False
    if per_sample:
        idxs = np.array([np.random.choice(x.size(1), size=num_permutations, replace=False) for _ in range(x.size(0))])
    else:
        idxs = np.array([np.random.choice(x.size(1), size=num_permutations, replace=False)] * x.size(0))
    swap = idxs[:, random_derangement(idxs.shape[1], rng=rng)]
    x_shuffled = x.clone()
    for row in range(x_shuffled.size(0)):
        x_shuffled[row][idxs[row]] = x_shuffled[row][swap[row]]
    return x_shuffled
    

@torch.no_grad()
def permutation_perturbations(model, dataset, num_permutations, num_perturbations_per_sample=10, seed=None, per_sample=True):
    """ Locally perturbs data by permuting certain indices and see how much the logits are perturbed. 
    
    Parameters:
    -----------
    model : torch.nn.Module
        The model to check
    dataset : torch_geometric.data.Dataset
        The dataset to investigate. Currently, only dataset is used.
    num_permutations : iterable
        Different magnitudes of noise to check.
    num_perturbations_per_sample : int
        How many random perturbations to use per sample and per noise magnitude.
    seed : int or None
        If given, seeds the rng and makes the perturbations deterministic.
    per_sample : bool
        If `True`, then the columns to be permuted are re-rolled for each row.
        If `False`, then the columns to be permuted are globally selected for all rows.
    
    Returns:
    --------
    perturbations : dict
        Mapping from the resulting input perturbation (l2 distance) -> ndarray of output perturbations.
    """
    if seed is None:
        seed = np.random.randint(1 << 32)
    rng = np.random.RandomState(seed)
    perturbations = np.sort(np.unique(np.linspace(1, dataset.x.size(1), num_permutations).astype(int))).tolist()

    h = model(dataset)[-1][dataset.mask].cpu()
    input_perturbations, output_perturbations = [], []
    for num_permutations in perturbations:
        for _ in range(num_perturbations_per_sample):
            x_perturbed = permute_features(dataset.x, num_permutations, rng=rng, per_sample=per_sample)
            h_perturbed = model(Data(x=x_perturbed, edge_index=dataset.edge_index))[-1][dataset.mask]
            input_perturbations.append((x_perturbed - dataset.x).norm(dim=1).cpu())
            output_perturbations.append((h_perturbed - h).norm(dim=1).cpu())
    input_perturbations = torch.cat(input_perturbations).numpy() # N * len(perturbations) * num_perturbations_per_sample
    output_perturbations = torch.cat(output_perturbations).numpy()  # N * len(perturbations) * num_perturbations_per_sample

    # Bin the data to avoid clutter
    bin_edges = np.histogram_bin_edges(input_perturbations, bins='auto')
    bin_idxs = np.digitize(input_perturbations, bin_edges)
    results = {}
    for bin_idx in np.unique(bin_idxs):
        result[0.5 * (bin_edges[bin_idx - 1] + bin_edges[bin_idx])] = output_perturbations[bin_idxs == bin_idx]
    return result