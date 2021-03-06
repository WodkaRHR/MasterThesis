import numpy as np
import matplotlib.pyplot as plt
from util import calibration_curve

def plot_calibration(probs, y_true, bins=10, eps=1e-12):
    """ Calculates the calibration curve for predictions.
    
    Parameters:
    -----------
    probs : torch.Tensor, shape [n, num_classes]
        Predicted probabilities.
    y_true : torch.Tensor, shape [n]
        True class labels.
    bins : int
        The number of bins to use.
    eps : float 
        Epsilon to prevent division by zero.
    
    Returns:
    --------
    fig : plt.Figure
        The figure plotted.
    axs : plt.Axes
        The axes of the figure.
    """
    edges, bin_conf, bin_acc, bin_density = calibration_curve(probs, y_true, bins=bins, eps=eps)
    widths = edges[1:] - edges[:-1]
    centers = 0.5 * (edges[1:] + edges[:-1])
    
    fig, axs = plt.subplots(2, 1, sharex=True, squeeze=False, gridspec_kw = {
            'height_ratios' : [0.85, 0.15],
    })
    ax = axs[0, 0]
    ax.plot([0, 1], [0, 1], ls='--')
    ax.bar(centers, bin_conf, widths, label='Confidence', alpha=0.5)
    ax.bar(centers, bin_acc, widths, label='Accuracy', alpha = 0.5)
    ax.legend()
    
    axs[1, 0].bar(centers, bin_density, widths, label='Density')
    
    return fig, axs