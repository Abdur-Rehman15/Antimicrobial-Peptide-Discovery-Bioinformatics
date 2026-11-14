"""Figure: why the negatives must be charge-filtered the same way as real candidates.

Compares real AMPs with random protein fragments (same length distribution) on three
descriptors, first unfiltered and then keeping only peptides with net charge >= +2.
Needs data/processed/positives_descriptors.csv and data/interim/random_windows_demo_descriptors.csv.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from amp_triage import config

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
AMP, RANDOM = "#2a78d6", "#eb6834"  # categorical slots 1 and 2 (validated)

amps = pd.read_csv(config.PROCESSED_DIR / "positives_descriptors.csv")
rand = pd.read_csv(config.INTERIM_DIR / "random_windows_demo_descriptors.csv")

panels = [
    ("net_charge", "Net charge at pH 7.4", np.arange(-8, 15, 1.0)),
    ("hydrophobic_fraction", "Water-repelling residues (fraction)", np.linspace(0, 1, 21)),
    ("hydrophobic_moment_helix", "Hydrophobic moment (two-faced helix)", np.linspace(0, 1.4, 29)),
]
rows = [("All peptides", 0.0), ("Only peptides with net charge \u2265 +2", 2.0)]

fig, axes = plt.subplots(2, 3, figsize=(12.5, 6.6), facecolor=SURFACE)
for r, (row_title, min_charge) in enumerate(rows):
    a = amps[amps.net_charge >= min_charge] if min_charge else amps
    b = rand[rand.net_charge >= min_charge] if min_charge else rand
    for c, (col, label, bins) in enumerate(panels):
        ax = axes[r, c]
        ax.set_facecolor(SURFACE)
        ax.hist(a[col], bins=bins, density=True, histtype="step", linewidth=2, color=AMP)
        ax.hist(b[col], bins=bins, density=True, histtype="step", linewidth=2, color=RANDOM)
        auc = roc_auc_score(np.r_[np.ones(len(a)), np.zeros(len(b))], np.r_[a[col], b[col]])
        ax.text(0.97, 0.95, f"separation (AUC) {auc:.2f}", transform=ax.transAxes,
                ha="right", va="top", fontsize=9.5, color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.set_yticklabels([])
        if r == 1:
            ax.set_xlabel(label, color=INK, fontsize=10.5)
        if c == 0:
            ax.set_ylabel(row_title, color=INK, fontsize=10.5, labelpad=8)

fig.suptitle("Net charge nearly separates AMPs from random protein pieces; once charge is "
             "filtered, other features must do the work", x=0.01, ha="left", color=INK,
             fontsize=13, fontweight="bold")
fig.text(0.01, 0.925, f"{len(amps):,} real AMPs vs {len(rand):,} random protein fragments of the "
         "same lengths. AUC 0.5 = no separation, 1.0 = perfect.", color=MUTED, fontsize=10)
handles = [plt.Line2D([], [], color=AMP, lw=2), plt.Line2D([], [], color=RANDOM, lw=2)]
fig.legend(handles, ["Real AMPs", "Random protein fragments"], loc="lower center", ncol=2,
           frameon=False, labelcolor=INK, fontsize=10.5, bbox_to_anchor=(0.5, -0.005))
fig.tight_layout(rect=(0, 0.04, 1, 0.93))
out = config.FIGURES_DIR / "descriptor_charge_filter.png"
fig.savefig(out, dpi=150, facecolor=SURFACE)
print("saved", out)
