''' Shared visual style for the "styled" system report (report_style="styled").

Defines the report-styling palette and a scoped matplotlib style so the report
charts (equity curve, trades, distribution, Monte Carlo, and - when
report_style="styled" - the per-ticker price and TA charts) share one
professional look. The style is applied through `report_style()`, a context
manager built on `plt.rc_context`, so it is active only for the wrapped
plotting block and is fully restored afterwards, leaving any classic-style
plots generated in the same run untouched. '''

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from cycler import cycler

# ---- palette (single accent, single neutral, two semantic colours) ----
ACCENT = "#534AB7"   # strategy
NEUTRAL = "#B4B2A9"  # benchmark
POS = "#3B6D11"      # wins / gains
NEG = "#A32D2D"      # losses
GRID = "#E5E3DC"     # gridlines / hairlines
TEXT = "#2C2C2A"     # body text
TEXT2 = "#5F5E5A"    # secondary text

# Diverging ramp for signed "share" measures that run loss -> gain (e.g. the
# fraction of its peak a trade kept). Built from the two semantic colours
# through a paper-toned midpoint, so it stays inside the palette and keeps the
# usual reading: red is adverse, green is favorable, pale is neutral/zero.
DIVERGING_CMAP = LinearSegmentedColormap.from_list("pos_neg_diverging",
                                                   [NEG, "#EFEDE6", POS])

# ---- secondary palette for the per-ticker and TA charts ----
# The per-ticker price / TA charts carry several overlay and indicator lines
# (EMA fast/mid/slow, SMA fast/slow, Chandelier exits, RSI/MACD/ADX/DI panels) that
# must stay distinguishable - more series than the strict 4-colour report
# palette above allows. These keep the classic charts' distinct green / brown /
# black moving-average hues (spread across the hue wheel and in value so the
# lines separate clearly to the eye), lightly refined to sit with the report
# look; the accent-purple Close line stays the dominant series.
IND_GREEN = "#1F9E5A"     # fast MA (EMA fast / SMA fast)
IND_BROWN = "#A5652B"     # mid MA  (EMA mid / SMA slow)
IND_CHARCOAL = "#454545"  # slow MA (EMA slow)
IND_GOLD = "#C8952F"      # SMA225 regime line / MACD signal

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
