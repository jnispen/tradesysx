''' Shared visual style for the "styled" system report (report_style="styled").

Defines the report-styling palette and a scoped matplotlib style so the
system-level report charts (equity curve, trades, distribution, Monte Carlo)
share one professional look. The style is applied through `report_style()`, a
context manager built on `plt.rc_context`, so it is active only for the wrapped
plotting block and is fully restored afterwards - the per-ticker and TA plots
generated in the same run are deliberately left untouched. '''

import matplotlib.pyplot as plt
from cycler import cycler

# ---- palette (single accent, single neutral, two semantic colours) ----
ACCENT = "#534AB7"   # strategy
NEUTRAL = "#B4B2A9"  # benchmark
POS = "#3B6D11"      # wins / gains
NEG = "#A32D2D"      # losses
GRID = "#E5E3DC"     # gridlines / hairlines
TEXT = "#2C2C2A"     # body text
TEXT2 = "#5F5E5A"    # secondary text

# rcParams baseline shared by every styled chart
REPORT_RC = {
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": GRID,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.prop_cycle": cycler(color=[ACCENT, NEUTRAL, POS, NEG]),
    "axes.titlesize": 13,
    "axes.titleweight": "medium",
    "axes.labelsize": 10,
    "axes.labelcolor": TEXT2,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "xtick.color": TEXT2,
    "ytick.color": TEXT2,
    "text.color": TEXT,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "font.family": "sans-serif",
    "figure.dpi": 150,
    "savefig.bbox": "tight",
}

# one consistent figure width across the whole report (heights may vary)
FIG_WIDTH = 7.6


def report_style():
    ''' context manager that applies the report style for its block only,
    restoring the previous rcParams on exit (so other plots are unaffected). '''
    return plt.rc_context(REPORT_RC)
