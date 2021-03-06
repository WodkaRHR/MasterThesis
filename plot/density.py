import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import torch
import matplotlib.colors as mcolors
from sklearn.decomposition import PCA
from scipy.stats import binned_statistic_2d
from openTSNE import TSNE
import umap
from util import is_outlier
from typing import Tuple, Dict, Any, List, Iterable

_tableaeu_colors = list(mcolors.TABLEAU_COLORS.keys())


def get_dimensionality_reduction_to_plot(features_to_fit: np.ndarray, featues_to_evaluate: np.ndarray, 
    dimensionality_reduction_types: Iterable[str], seed: int = 1337, num_bins: int = 20) -> Tuple[
        Dict[str, np.ndarray], np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """ Prepares dimensionality reductions to plot by calculating an embedding and creating a grid with inverse transform under the embedding.
    
    Parameters:
    -----------
    features_to_fit : ndarray, shape [N, D]
        The features to fit
    features_to_evaluate : ndarray, shape [N', D]
        The features to evaluate.
    dimensionality_reduction_types : Iterable[str]
        Which dimensionality reductions to perform.
    seed : int, optional
        The seed for the dimensionality reductions.
    num_bins : int, optional
        The grid resolution in bins.
    
    Returns:
    --------
    embeddings : dict
        A mapping from `dimensionality_reduction_type` to np.ndarray, shape [N + N', 2] giving the embeddings of points.
    is_train : np.ndarray, shape [N + N']
        Boolean indicator for the points in `embeddings.values()` if they are part of the training data.
    grids : dict
        Mapping from `dimensionality_reduction_type` to np.ndarray, shape [num_bins, num_bins, 2] giving the embedded grid coordinates.
    grid_inverses : dict
        Mapping from `dimensionality_reduction_type` to np.ndarray, shape [num_bins, num_bins, D] giving the inverses of the grids.
    """
    points_to_plot = np.concatenate([features_to_fit, featues_to_evaluate], 0)
    is_train = np.concatenate([np.ones(features_to_fit.shape[0], dtype=bool), np.zeros(featues_to_evaluate.shape[0], dtype=bool)], 0)
    plotting_projections, embeddings, grids, grid_inverses = {}, {}, {}, {}

    for plotting_type in dimensionality_reduction_types:
        if plotting_type.lower() == 'pca':
            plotting_projections[plotting_type] = PCA(n_components=2, random_state=1337)
            plotting_projections[plotting_type].fit(points_to_plot)
        elif plotting_type.lower() == 'umap':
            plotting_projections[plotting_type] = umap.UMAP(random_state = 1337)
            plotting_projections[plotting_type].fit(points_to_plot)
        else:
            raise ValueError(f'Cant plot density with dimensionality reduction {plotting_type}')
        embeddings[plotting_type] = plotting_projections[plotting_type].transform(points_to_plot)
        mins, maxs = embeddings[plotting_type].min(0), embeddings[plotting_type].max(0)
        mins, maxs = mins - 0.1 * (maxs - mins), maxs + 0.05 * (maxs - mins) # Gives a margin for the density map
        
        xx, yy = np.meshgrid(np.linspace(mins[0], maxs[0], num_bins), np.linspace(mins[1], maxs[1], num_bins), indexing='ij')

        grids[plotting_type] = np.stack((xx, yy), axis=-1)
        grid_inverses[plotting_type] = plotting_projections[plotting_type].inverse_transform(grids[plotting_type].reshape(-1, 2)).reshape((num_bins, num_bins, -1))

    return embeddings, is_train, grids, grid_inverses


def plot_density(embeddings_fit: np.ndarray, embeddings_eval: np.ndarray, grid: np.ndarray, 
                 density: np.ndarray, labels : np.ndarray, 
                    label_names: Dict[int, str], levels: int = 20, 
                 alpha: float = 0.5, cmap='Reds', vmin=None, vmax=None, colors={}, cols=2,
                label_order = None, legend_labels = None, color_fit=None, legend_x=1.08):

    """ Makes a 2d density plot that contains points that were used to fitting and one subplot for each label that is to be evaluated.
    
    Parameters:
    -----------
    embeddings_fit : ndarray, shape [N_fit, 2]
        Points used for fitting. Will be in every subplot.
    embeddings_eval : ndarray, shape [N_eval, 2]
        Points used for evaluation.
    grid : ndarray, shape [nx, ny, 2]
        Grid coordinates for the density plot.
    density : ndarray, shape [nx, ny]
        Values for the density grid.
    labels : ndarray, shape [N_eval]
        Labels for data used in evaluation. Each label gets its own subplot.
    label_names : Dict[Any, str].
        Names for each label in `labels`.
    levels : int, optional, default: 20
        Number of levels to include int he density contour plot.
    alpha : float, optional, default: 0.5
        Alpha value for scatter points.
    cmap : Union[str, mcolors.Colormap]
        The colormap to use for the density contour plot.
    vmin : float, optional
        Minimal value to plot in the density. If not given, the minimum of `density` is used.
    vmax : float, optional
        Maximal value to plot in the density. If not given, the maximum of `density` is used.
    colors : dict, optional
        Mapping from label to color. If None is given, default plt colors are used.
    cols : int, default: 2
        How many columns to use for subplots.
    label_order : list, optional
        Order in which the labels will be plotted. If None, labels `label_names` will be sorted.
    legend_labels : Union[Dict, List, Tuple]
        Which labels will be part of the legend. If None, all labels in `label_names` will be used.
        If a dict is given, the values will be used to annotate the legend.
    color_fit : Union[str, Iterable], optional
        The color used for the embedding points used for fitting.

    Returns:
    --------
    fig : plt.Figure
        The figure
    axs : ndarray
        The axes of the plot. 
    """ 
    
    rows = int(np.ceil(len(label_names) / cols))
    
    if vmax is None:
        vmax = density.max()
    if vmin is None:
        vmin = density.min()
    if label_order is None:
        label_order = sorted([l for l in label_names.keys() if l in label_names])
    if legend_labels is None:
        legend_labels =  dict(label_names)
    
    fig, axs = plt.subplots(rows, cols, figsize=(5 * cols, 4 * rows), squeeze=False)
    all_embeddings = np.concatenate([embeddings_fit, embeddings_eval], 0)
    
    legend_handles = []
    label_fit_in_handles = False # The Label "fit" should only be included once in the legend
    
    for idx, label in enumerate(label_order):
        name = label_names[label]
        if isinstance(legend_labels, dict) and label in legend_labels:
            legend_label = legend_labels[label]
        else:
            legend_label = name

        ax = axs[idx // cols, idx % cols]
        c = ax.contourf(grid[:, :, 0], grid[:, :, 1], density, cmap=cmap, levels=np.linspace(vmin, vmax, levels+1), extend='both', vmin=vmin, vmax=vmax)
        ax.scatter(embeddings_fit[:, 0], embeddings_fit[:, 1], label='Fit' if not label_fit_in_handles else None, marker='1', alpha=alpha, color=color_fit)
        points_to_plot = embeddings_eval[(labels == label)]
        ax.scatter(points_to_plot[:, 0], points_to_plot[:, 1], label=legend_label, marker='x', alpha=alpha, color=colors.get(label, None))
        ax.tick_params(
            axis='both',          
            which='both',      
            bottom=False,
            labelbottom=False,
            labelleft=False,
            left=False,
        )
        ax.set_title(name)

        emb_mins, emb_maxs = all_embeddings.min(0), all_embeddings.max(0)
        emb_mins, emb_maxs = emb_mins - 0.05 * (emb_maxs - emb_mins), emb_maxs + 0.05 * (emb_maxs - emb_mins)
        
        ax.set_xlim(left = emb_mins[0], right = emb_maxs[0])
        ax.set_ylim(bottom = emb_mins[1], top = emb_maxs[1])
        
        if label in legend_labels:
            legend_handles.append(ax.get_legend_handles_labels())
            label_fit_in_handles = True
    
    lines, labels = [sum(lol, []) for lol in zip(*legend_handles)]
    fig.legend(lines, labels, loc = 'upper right', bbox_to_anchor = (0,-0.1,legend_x,1),
            bbox_transform = plt.gcf().transFigure)
    

    fig.colorbar(c, ax=axs.ravel().tolist(),location = 'left')

    return fig, axs
    

# def plot_density(points_to_fit, points_to_eval, density_model, labels, label_names, 
#                 seed=1337, bins=20, levels=20, dimensionality_reduction='umap', num_samples=50000,
#             sampling_stragey = 'random', alpha=0.5):
#     """ Creates a density plot for high dimensional points by using dimensionality reduction. 
#     Also visualizes the density by creating a meshgrid in 2d space
#     and using the inverse transform to find densities for these points or sampling.
    
#     Parameters:
#     -----------
#     points_to_fit : torch.Tensor, shape [N, D]
#         The points the density model was fit to.
#     points_to_eval : torch.Tensor, shape [N', D]
#         The points the density model is evaluated on.
#     density_model : nn.Module
#         A callable module that evaluates the density for points of shape (*, D)
#     labels : torch.Tensor, shape [N']
#         Labels for the points to evaluate.
#     label_names : dict
#         A  mapping that names the points to evaluate.
#     seed : int
#         The seed for the PCA.
#     bins : int
#         How many bins to use for the meshgrid.
#     levels : int
#         How many contour levels to plot.
#     dimensionality_reduction : 'pca' or 'tsne' or 'umap'
#         How to reduce the dimensionality of the points.
#     sampling_strategy : 'random', 'convex_combinations', 'normal'
#         How to sample points to find densities over a meshgrid in non invertible dimensionality reductions.
#     alpha : float
#         Alpha value for plots.

#     Returns:
#     --------
#     plt.Figure
#         The plot.
#     plt.axis.Axes
#         The axis of the plot.
#     """
    
#     bins_x, bins_y = bins, bins
#     dimensionality_reduction = dimensionality_reduction.lower()
#     sampling_stragey = sampling_stragey.lower()
#     points_to_fit = points_to_fit.cpu()
#     points_to_eval = points_to_eval.cpu()
#     points = torch.cat([points_to_fit, points_to_eval], 0)
    
    
#     if dimensionality_reduction == 'tsne':
#         proj = TSNE(random_state = seed).fit(points.numpy())
#     elif dimensionality_reduction == 'pca':
#         proj = PCA(n_components=2, random_state=seed)
#         proj.fit(points.numpy())
#     elif dimensionality_reduction == 'umap':
#         proj = umap.UMAP(random_state = seed)
#         proj.fit(points.numpy())
#     else:
#         raise RuntimeError(f'Unsupported dimensionality reduction {dimensionality_reduction}')
    
#     emb_to_fit = proj.transform(points_to_fit)
#     emb_to_eval = proj.transform(points_to_eval)
#     emb = np.concatenate([emb_to_fit, emb_to_eval], 0)
    
#     if hasattr(proj, 'inverse_transform'):
#         # Use the inverse transform of the projection
#         mins, maxs = emb.min(0), emb.max(0)
#         mins, maxs = mins - 0.1 * (maxs - mins), maxs + 0.05 * (maxs - mins) # Gives a margin for the density map
#         xx, yy = np.meshgrid(np.linspace(mins[0], maxs[0], bins_x), np.linspace(mins[1], maxs[1], bins_y), indexing='ij')
#         xx, yy = xx.reshape((-1, 1)), yy.reshape((-1, 1))
#         grid = np.concatenate((xx, yy), axis=-1)
        
#         density_grid = density_model(torch.tensor(proj.inverse_transform(grid)).float()).cpu().numpy()
#         xx, yy, density_grid = xx.reshape((bins_x, bins_y)), yy.reshape((bins_x, bins_y)), density_grid.reshape((bins_x, bins_y))
#     else:
#         # Sample points within the box of the original data
#         mins, maxs = points.min(0)[0], points.max(0)[0]
#         mins, maxs = mins - 0.1 * (maxs - mins), maxs + 0.1 * (maxs - mins) # Gives a margin for the density map
#         if sampling_stragey == 'random':
#             samples = torch.rand(num_samples, points.size(1))
#             samples *= maxs - mins
#             samples += mins
#         elif sampling_stragey == 'convex_combinations':
#             k = 4 # This many points are in each convex combination
#             coefs_mask = torch.zeros(num_samples, emb.shape[0])
#             selected = torch.argsort(torch.randn(*coefs_mask.size()), 1)[:, :k]
#             for row in range(selected.size(0)):
#                 coefs_mask[row][selected[row].tolist()] = 1.0
            
#             coefs = torch.rand(*coefs_mask.size()) * coefs_mask
#             coefs /= 0.25 * coefs.sum(1)[:, None]
#             samples = coefs @ points
#         elif sampling_stragey == 'normal':
#             samples = torch.randn(num_samples, points.size(1))
        
#         else:
#             raise RuntimeError(f'Unknown sampling strategy for high dimesional space {sampling_stragey}')
        
#         samples = torch.cat([samples, points])
        
#         density_samples = density_model(samples).cpu().numpy()
#         samples_emb = proj.transform(samples.numpy())
        
#         density_grid, bins_x, bins_y, _ = binned_statistic_2d(
#         samples_emb[:, 0], samples_emb[:, 1], density_samples, bins=(bins, bins))
#         density_grid = density_grid.T
#         bins_x, bins_y = 0.5 * (bins_x[1:] + bins_x[:-1]), 0.5 * (bins_y[1:] + bins_y[:-1])
#         xx, yy = np.meshgrid(bins_x, bins_y)
    
    
#     fig, ax = plt.subplots(1, 1)
#     c = ax.contourf(xx, yy, density_grid, cmap='Reds', levels=levels)
#     fig.colorbar(c, ax=ax)
#     #ax.scatter(samples_emb[:, 0], samples_emb[:, 1], c=density_samples)
#     ax.scatter(emb_to_fit[:, 0], emb_to_fit[:, 1], label='Fit', marker='1', alpha=alpha)
#     for label, name in label_names.items():
#         points_to_plot = emb_to_eval[labels == label]
#         ax.scatter(points_to_plot[:, 0], points_to_plot[:, 1], label=name, marker='x', alpha=alpha)
    
#     emb_mins, emb_maxs = emb.min(0), emb.max(0)
#     emb_mins, emb_maxs = emb_mins - 0.05 * (emb_maxs - emb_mins), emb_maxs + 0.05 * (emb_maxs - emb_mins)
    
#     ax.set_xlim(left = emb_mins[0], right = emb_maxs[0])
#     ax.set_ylim(bottom = emb_mins[1], top = emb_maxs[1])
#     ax.legend()
#     return fig, ax


def plot_2d_log_density(points, labels, density_model, resolution=100, levels=10, label_names=None):
    """ Makes a 2d log-density plot of a space. 
    
    Parameters:
    -----------
    points : torch.tensor, shape [N, 2]
        points to place as points in the density space.
    labels : torch.tensor, shape [N]
        Labels for the points to place (will be added to the legend).
    density_model : torch.nn.Module
        A model that evaluates the logit space density.
    resolution : int
        Resolution for the plot. Default: 100
    levels : int
        How many countour levels. Default: 10
    label_names : dict or None
        Names of the labels. If None is given, each label is rerred to by its number.
    
    Returns:
    --------
    plt.Figure
        The plot.
    plt.axis.Axes
        The axis of the plot.
    """
    points = points.cpu().numpy()
    labels = labels.cpu().numpy()

    if points.shape[1] != 2:
        print(f'Cant plot 2d density for logit space of dimension {points.shape[1]}')
        return None, None

    if label_names is None:
        label_names = {label : f'{label}' for label in np.unique(labels)}

    density_model = density_model.cpu()

    (xmin, ymin), (xmax, ymax) = points.min(axis=0), points.max(axis=0)
    mesh = np.array(np.meshgrid(np.linspace(xmin, xmax, resolution), np.linspace(ymin, ymax, resolution))).reshape(2, -1).T
    mesh = torch.tensor(mesh)
    mesh_log_density = np.log(density_model(mesh).cpu().numpy().T.reshape(resolution, resolution))
    xx, yy = mesh.cpu().numpy().T.reshape(2, resolution, resolution)
    fig, ax = plt.subplots(1, 1)
    ax.contourf(xx, yy, mesh_log_density, levels=20)
    for label, name in label_names.items():
        ax.scatter(points[:, 0][labels==label], points[:, 1][labels==label], c=_tableaeu_colors[label], label=name, marker='x', linewidth=1.0)
    ax.legend()
    return fig, ax
