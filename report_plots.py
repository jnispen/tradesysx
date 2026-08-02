''' Styled report charts (used when report_style="styled").

These are the redesigned versions of the system-level charts (equity/balance,
trades, trade distribution, Monte Carlo) and the per-ticker charts (price,
TA, custom-TA and benchmark price), following the report-styling palette and
rules (no boxed stat overlays inside the axes, wins green / losses red, equity
in the accent colour, benchmark as a dashed neutral reference line, thousands
separators on money axes). Each function saves a PNG to the same path its
classic counterpart uses, so the rest of the pipeline is unaffected; the
styled summary report then embeds those PNGs.

All plotting runs inside `report_style()` so the styling is scoped to these
charts only and any classic-style plots generated in the same run stay
untouched. The per-ticker / TA charts keep the wide monitoring format and pass
explicit larger font sizes (the shared rcParams are tuned for the narrower
system-level report figures). '''

import logging

import numpy as np
import pandas as pd
import talib as ta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.ticker import StrMethodFormatter, AutoLocator
from matplotlib.offsetbox import TextArea, DrawingArea, HPacker, AnchoredOffsetbox

from matplotlib.colors import TwoSlopeNorm, to_rgb
from matplotlib.patches import Rectangle, FancyBboxPatch

from tradesysx.report_style import (report_style, ACCENT, NEUTRAL, NEUTRAL_DARK,
                                    POS, NEG, GRID, TEXT, TEXT2, WARN, IND_GREEN,
                                    IND_BROWN, IND_CHARCOAL, IND_GOLD,
                                    DIVERGING_CMAP, FIG_WIDTH)

logger = logging.getLogger(__name__)

# The per-ticker / TA charts keep the classic wide monitoring format (28in) so a
# full multi-year daily history stays legible. The shared report rcParams set
# small type sizes tuned for the narrow report figures, so these charts pass
# explicit larger sizes to stay readable at the wider scale.
_TITLE_FS = 22   # figure suptitle
_SIG_FS = 17     # signal callout
_ANN_FS = 13     # corner annotations (trade details, R-average, date)
_AX_FS = 14      # axis labels
_TICK_FS = 12    # tick labels
_LEG_FS = 12     # legend

# Empty band kept under the data on a price panel (as a fraction of the data
# range) for the text that sits along its bottom edge - see reserve_bottom_band.
# The legend plus the EUR line above it needs more room than the single
# R-average line.
_EUR_LINE_BAND = 0.14
_R_AVERAGE_BAND = 0.07


# Reader-facing names for the position-sizing keys used in conf['pos_sizing'].
_POS_SIZING_LABELS = {
    'core_equity_risk': 'Core equity risk',
    'fixed_dollar_risk': 'Fixed dollar risk',
    'fixed_ratio': 'Fixed ratio',
    'fixed_amount': 'Fixed amount',
    'kelly': 'Kelly criterion',
}


def pos_sizing_label(conf):
    ''' friendly name for conf['pos_sizing'], falling back to a de-underscored
    title-case of the raw key for any method not in the map. For the kelly
    method the configured kelly fraction is appended between brackets. '''
    key = conf.get('pos_sizing', '')
    label = _POS_SIZING_LABELS.get(key, key.replace('_', ' ').capitalize())
    if key == 'kelly':
        label += f" ({conf['kelly_ratio']})"
    return label


def _thousands(ax):
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))


class _NonNegativeLocator(AutoLocator):
    ''' the default tick locator with the ticks below zero dropped. A price panel
    opens extra room under the data for the legend and the EUR line (see
    _text_above_legend), which on a ticker whose range starts near zero pushes
    the axis under it - and a negative price tick reads as if the stock could
    trade there. The empty band stays, the ticks do not. Locating (rather than
    formatting) keeps it right when the y range is changed after the axis is
    styled, and drops the stray gridline with the label. '''

    def tick_values(self, vmin, vmax):
        ticks = super().tick_values(vmin, vmax)
        return ticks[ticks >= 0]


def styled_balance_plot(df, conf, ctx, val_out):
    ''' equity curve: simulated account value (accent) vs the buy-and-hold
    benchmark drawn as a dashed neutral reference line at its final value. '''

    df = df.copy()
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
    df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce')
    # do_balance_simulation returns the frame with Date already reformatted to
    # day-first '%d-%m-%Y' (see utils.do_balance_simulation); parse it as such so
    # points stay in chronological order (the classic balance_plot uses dayfirst=True).
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y', errors='coerce')
    eq = df.dropna(subset=['Value', 'Date']).sort_values('Date')

    # the mark-to-market Value series stops at the last trade event; the
    # simulation then force-closes any still-open positions at the final close
    # (those rows carry Balance but no Value). Extend the curve to that final
    # liquidated balance on the close date so it ends on the reported final
    # balance rather than the last event's mark-to-market value.
    xs = list(eq['Date']); ys = list(eq['Value'])
    close_date = df['Date'].iloc[-1]
    final_balance = df['Balance'].iloc[-1]
    if pd.notna(close_date) and pd.notna(final_balance):
        xs.append(close_date); ys.append(final_balance)
    end_x, end_y = xs[-1], ys[-1]

    with report_style():
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.6))
        ax.plot(xs, ys, color=ACCENT, lw=1.8, label='Strategy')

        start = float(conf['balance'])
        ax.axhline(start, color=NEUTRAL, lw=0.8, ls=':')

        if val_out is not None:
            # end the dashed line at the last data point (not the full axes
            # width) so the value label printed just past it isn't crossed.
            ax.plot([min(xs), end_x], [val_out, val_out],
                    color=NEUTRAL, lw=1.6, ls='--', label='Buy & hold')
            ax.annotate(f"{val_out:,.0f}", (end_x, val_out),
                        xytext=(8, 0), textcoords='offset points', va='center',
                        color=TEXT2, fontsize=9)

        ax.annotate(f"{end_y:,.0f}", (end_x, end_y),
                    xytext=(6, 0), textcoords='offset points', va='center',
                    color=ACCENT, fontsize=9, fontweight='medium')

        ax.grid(axis='y'); ax.grid(axis='x', visible=False)
        _thousands(ax)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.set_ylabel('Account value (USD)')
        ax.set_xlim(min(xs), end_x + pd.Timedelta(days=120))
        if val_out is not None:
            ax.legend(loc='upper left')
        fig.savefig(ctx.outpath('images', 'balance_plot.png'))
        plt.close(fig)


def styled_equity_plot(df, conf, ctx, val_out, max_recovery=0, rec_from=None, rec_to=None,
                       bm_curve=None):
    ''' daily equity curve from the equity table: total equity (accent) against
    the buy-and-hold benchmark, with the drawdown from the running equity peak
    (%), the trailing one-year return ($) and the monthly return in panels below
    it. Unlike styled_balance_plot this walks the trading calendar, so the
    x-axis is real time rather than the trade-event sequence.

    When `bm_curve` (a pd.Series of the benchmark's daily value, indexed by date)
    is given, the benchmark is drawn as a thin neutral curve over time, with
    `val_out` annotated at its end. '''

    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Equity'] = pd.to_numeric(df['Equity'], errors='coerce')
    df['Trail1Y'] = pd.to_numeric(df['Trail1Y'], errors='coerce')
    df['MonthRet'] = pd.to_numeric(df['MonthRet'], errors='coerce')
    df['DDPerc'] = pd.to_numeric(df.get('DDPerc'), errors='coerce')
    eq = df.dropna(subset=['Date', 'Equity']).sort_values('Date')
    if eq.empty:
        logger.warning("No equity data to plot")
        return

    xs, ys = eq['Date'], eq['Equity']
    end_x, end_y = xs.iloc[-1], ys.iloc[-1]
    xlim = (xs.iloc[0], end_x + pd.Timedelta(days=120))

    with report_style():
        fig, (ax, ax_dd, ax2, ax3) = plt.subplots(
            4, 1, figsize=(FIG_WIDTH, 8.2), sharex=True,
            gridspec_kw={'height_ratios': [3, 1.4, 1.6, 1.6], 'hspace': 0.12})

        ax.plot(xs, ys, color=ACCENT, lw=1.4, label='Strategy')
        ax.axhline(float(conf['balance']), color=NEUTRAL, lw=0.8, ls=':')

        # benchmark value over time (thin neutral curve), labelled at its final
        # value. The buy-and-hold end value is in the report tables as well, so
        # the curve alone carries it here - no flat reference line.
        bm_drawn = False
        if bm_curve is not None and not bm_curve.dropna().empty:
            bm_y = bm_curve.reindex(xs)
            ax.plot(xs, bm_y, color=NEUTRAL, lw=0.5, label='Buy & hold')
            bm_drawn = True
            if val_out is not None:
                ax.annotate(f"{val_out:,.0f}", (end_x, val_out),
                            xytext=(8, 0), textcoords='offset points', va='center',
                            color=TEXT2, fontsize=9)

        ax.annotate(f"{end_y:,.0f}", (end_x, end_y),
                    xytext=(6, 0), textcoords='offset points', va='center',
                    color=ACCENT, fontsize=9, fontweight='medium')

        ax.grid(axis='y'); ax.grid(axis='x', visible=False)
        _thousands(ax)
        ax.set_ylabel('Account value (USD)')
        if bm_drawn:
            ax.legend(loc='upper left')

        # drawdown from the running equity peak (%), directly under the equity
        # curve it belongs to. Always <= 0: the zero line is where the account
        # makes a new high, and the width of each excursion below it is the time
        # spent underwater. Drawn as an unfilled neutral line, like the benchmark
        # curve above - a red filled area reads as alarming out of proportion to
        # what it measures.
        dd = eq.dropna(subset=['DDPerc'])
        callout = (f"Longest drawdown: {max_recovery} days "
                   f"({rec_from:%Y-%m-%d} → {rec_to:%Y-%m-%d})"
                   if rec_from is not None and rec_to is not None else None)

        # the callout belongs with the curve it describes, but it must not land
        # on it - and where the curve is deep varies per run. So the y-limit is
        # stretched past the deepest excursion to reserve a band that no data can
        # reach (24% of the panel with the callout, against ~10% of text height),
        # and the text is placed inside that band. Clearance then holds whatever
        # the drawdown profile looks like.
        headroom = 1.32 if callout else 1.1
        ax_dd.axhline(0, color=TEXT2, lw=0.8)
        if not dd.empty:
            ax_dd.plot(dd['Date'], dd['DDPerc'], color=NEUTRAL, lw=0.8)
            ax_dd.set_ylim(min(dd['DDPerc'].min() * headroom, -1.0), 0)
            # current drawdown at the last close, annotated at the end of the
            # curve like the equity and trailing-return panels. The hyphen is
            # swapped for a true minus so it matches the y-tick labels.
            dd_end = float(dd['DDPerc'].iloc[-1])
            ax_dd.annotate(f"{dd_end:,.1f}%".replace('-', '−'),
                           (dd['Date'].iloc[-1], dd_end),
                           xytext=(6, 0), textcoords='offset points', va='center',
                           color=TEXT2, fontsize=9)

        if callout:
            ax_dd.text(0.98, 0.04, callout, transform=ax_dd.transAxes,
                       ha='right', va='bottom', color=TEXT2, fontsize=9)

        ax_dd.grid(axis='y'); ax_dd.grid(axis='x', visible=False)
        ax_dd.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}%"))
        ax_dd.set_ylabel('Drawdown (%)')

        # trailing one-year return in $: gains above the zero line green, losses
        # red. The first year has no full look-back window and stays blank.
        roll = eq.dropna(subset=['Trail1Y'])
        ax2.axhline(0, color=TEXT2, lw=0.8)
        if not roll.empty:
            ax2.fill_between(roll['Date'], roll['Trail1Y'], 0,
                             where=roll['Trail1Y'] >= 0, color=POS, alpha=0.25,
                             interpolate=True, linewidth=0)
            ax2.fill_between(roll['Date'], roll['Trail1Y'], 0,
                             where=roll['Trail1Y'] < 0, color=NEG, alpha=0.25,
                             interpolate=True, linewidth=0)
            ax2.plot(roll['Date'], roll['Trail1Y'], color=ACCENT, lw=1.0)
            ax2.annotate(f"{roll['Trail1Y'].iloc[-1]:,.0f}",
                         (roll['Date'].iloc[-1], roll['Trail1Y'].iloc[-1]),
                         xytext=(6, 0), textcoords='offset points', va='center',
                         color=ACCENT, fontsize=9)

        ax2.grid(axis='y'); ax2.grid(axis='x', visible=False)
        ax2.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax2.set_ylabel('Trailing 1y (USD)')

        # monthly return in $, booked on the last trading day of each month
        months = eq.dropna(subset=['MonthRet'])
        ax3.axhline(0, color=TEXT2, lw=0.8)
        if not months.empty:
            colors = [POS if v >= 0 else NEG for v in months['MonthRet']]
            ax3.bar(months['Date'], months['MonthRet'], width=22,
                    color=colors, alpha=0.85, linewidth=0)

        ax3.grid(axis='y'); ax3.grid(axis='x', visible=False)
        _thousands(ax3)
        ax3.set_ylabel('p/mo (USD)')
        ax3.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax3.set_xlim(*xlim)

        fig.savefig(ctx.outpath('images', 'equity_plot.png'))
        plt.close(fig)


def styled_monthly_dist_plot(df, ctx):
    ''' histogram of the monthly returns in $, positive months green / negative
    red, with the mean marked. Shows how the equity curve's month-to-month
    results are spread rather than how they accumulate. '''

    months = pd.to_numeric(df['MonthRet'], errors='coerce').dropna().to_numpy()
    if len(months) == 0:
        logger.warning("No monthly returns to plot")
        return

    # round the bin edges out to a whole $1000 so the bins land on readable
    # boundaries and the zero line falls on an edge, not inside a bin
    step = 1000.0
    lo = float(np.floor(months.min() / step) * step)
    hi = float(np.ceil(months.max() / step) * step)
    bins = np.arange(lo, hi + step, step)

    wins = months[months >= 0]; losses = months[months < 0]

    with report_style():
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.2))
        hist_kw = dict(bins=bins, alpha=0.9, rwidth=0.82, edgecolor='white', linewidth=0.6)
        ax.hist(wins, color=POS, label='Positive months', **hist_kw)
        ax.hist(losses, color=NEG, label='Negative months', **hist_kw)
        ax.axvline(0, color=TEXT2, lw=0.8)

        mean = months.mean()
        ax.axvline(mean, color=ACCENT, lw=1.2, ls='--', label='Mean')
        # placed via the x-data/y-axes-fraction blended transform so it sits just
        # above the plot area regardless of bar height, and never overlaps a bar
        ax.text(mean, 1.02, f"{mean:,.0f}", transform=ax.get_xaxis_transform(),
                ha='center', va='bottom', color=ACCENT, fontsize=9)

        ax.text(0.02, 0.95, "Max.\nMin.\nStd.", transform=ax.transAxes,
                ha='left', va='top', color=TEXT2, fontsize=9)
        ax.text(0.16, 0.95, f"{months.max():,.0f}\n{months.min():,.0f}\n{months.std(ddof=1):,.0f}",
                transform=ax.transAxes, ha='right', va='top',
                color=TEXT2, fontsize=9)

        ax.grid(axis='y'); ax.grid(axis='x', visible=False)
        ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.set_xlabel('Monthly return (USD)')
        ax.set_ylabel('Number of months')
        ax.legend(loc='upper right')
        fig.savefig(ctx.outpath('images', 'monthly_dist_plot.png'))
        plt.close(fig)


# ---- portfolio composition figure -------------------------------------------
# An open position sitting below this many R has not yet earned room above its
# stop (a trade at entry already stands 1 R above it), so its tile is flagged.
_PF_WARN_R = 1.0
_PF_COLS = 4          # tiles per row
_PF_GAP = 0.035       # gap between tiles, as a fraction of the grid width
_PF_LABEL_MIN = 6.0   # bar segments narrower than this % are left unlabelled
_PF_CASH = 'Cash'


def _pf_mix(colour, weight, base='white'):
    ''' blend `colour` towards `base` by `weight` (0 = colour, 1 = base) '''
    a, b = to_rgb(colour), to_rgb(base)
    return tuple(a[i] * (1 - weight) + b[i] * weight for i in range(3))


def _pf_minus(text):
    ''' hyphen -> true minus sign, per the report's number formatting rules '''
    return text.replace('-', '−')


def _pf_contrast(fore, back):
    ''' WCAG contrast ratio between two colours '''
    def relative_luminance(colour):
        channels = to_rgb(colour)
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                  for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    a, b = relative_luminance(fore), relative_luminance(back)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _pf_label_colour(fill):
    ''' the label colour that reads on `fill`.

        The bar's accent ramp runs light enough that white text falls under 3:1
        on its paler segments, so the colour is chosen per segment rather than
        fixed - white on the dark end, body text on the light end. '''
    return 'white' if _pf_contrast('white', fill) >= _pf_contrast(TEXT, fill) else TEXT


def _pf_bar(ax, cash, positions, equity):
    ''' part one: the whole account as a single 0-100% bar, one segment per
    open position by weight and the cash balance last. Segments too narrow to
    label are covered by one bracket - their exact shares are on the tiles. '''

    widths = [p['value'] / equity * 100 for p in positions]

    # Single-hue accent ramp, dark to light by rank. It is split in two bands
    # rather than run straight: white text on this hue only survives while the
    # tint stays near full strength, and body text only starts reading once it
    # is well lightened - between the two is a dead zone where neither clears
    # 4.5:1. So the segments wide enough to be labelled share the dark band, and
    # the unlabelled tail (which carries no text) spreads over the light one.
    labelled = [i for i, w in enumerate(widths) if w >= _PF_LABEL_MIN]
    tail_idx = [i for i, w in enumerate(widths) if w < _PF_LABEL_MIN]

    tints = {}
    for rank, i in enumerate(labelled):
        tints[i] = 0.00 + 0.16 * (rank / max(1, len(labelled) - 1))
    for rank, i in enumerate(tail_idx):
        tints[i] = 0.34 + 0.38 * (rank / max(1, len(tail_idx) - 1))

    segments = [(p['ticker'], w, _pf_mix(ACCENT, tints[i]))
                for i, (p, w) in enumerate(zip(positions, widths))]
    segments.append((_PF_CASH, cash / equity * 100, NEUTRAL_DARK))

    x = 0.0
    tail = []
    for name, width, colour in segments:
        ax.add_patch(Rectangle((x, 0), width, 1, facecolor=colour,
                               edgecolor='white', lw=0.9))
        centre = x + width / 2
        if width >= _PF_LABEL_MIN:
            label_colour = _pf_label_colour(colour)
            ax.text(centre, 0.60, name, ha='center', va='center', fontsize=8.5,
                    fontweight='semibold', color=label_colour)
            ax.text(centre, 0.28, '{:.1f}%'.format(width), ha='center',
                    va='center', fontsize=7.5, color=label_colour)
        else:
            tail.append((centre, width))
        x += width

    if tail:
        lo = tail[0][0] - tail[0][1] / 2
        hi = tail[-1][0] + tail[-1][1] / 2
        total = sum(w for _, w in tail)
        ax.plot([lo, lo, hi, hi], [-0.14, -0.30, -0.30, -0.14],
                color=NEUTRAL, lw=0.8, clip_on=False)
        ax.text((lo + hi) / 2, -0.44,
                '{} position{}  ·  {:.1f}%'.format(
                    len(tail), '' if len(tail) == 1 else 's', total),
                ha='center', va='top', fontsize=7.5, color=TEXT2)

    # only the scale's ends, printed under the bar
    ax.text(0, -0.12, '0%', ha='left', va='top', fontsize=7, color=TEXT2)
    ax.text(100, -0.12, '100%', ha='right', va='top', fontsize=7, color=TEXT2)

    ax.set_xlim(0, 100)
    ax.set_ylim(-0.62, 1.05)
    ax.axis('off')


def _pf_cells(cash, positions, max_tiles):
    ''' the tiles to draw: the largest positions, an aggregate tile for whatever
    the cap leaves out, and the cash balance last. '''

    # below three there is no room for a position, the aggregate and the cash
    max_tiles = max(3, max_tiles)
    cells = list(positions)
    if len(cells) + 1 > max_tiles:
        shown, rest = cells[:max_tiles - 2], cells[max_tiles - 2:]
        cells = shown + [{'ticker': '+{} others'.format(len(rest)),
                          'value': sum(p['value'] for p in rest),
                          'gain': sum(p['gain'] for p in rest),
                          'aggregate': True}]
    return cells + [{'ticker': _PF_CASH, 'value': cash, 'cash': True}]


def _pf_tile(ax, cell, x, y, size):
    ''' one square tile. Green when the position's open R is positive, red when
    it is negative, neutral for the cash and aggregate tiles. The right-hand
    column of numbers stays flush across every tile, so the warning dot sits in
    the top-left corner and indents the ticker instead. '''

    is_cash = cell.get('cash', False)
    is_aggregate = cell.get('aggregate', False)
    plain = is_cash or is_aggregate

    if plain:
        semantic = NEUTRAL_DARK if is_cash else (POS if cell['gain'] > 0 else NEG)
    else:
        semantic = POS if cell['rmul'] > 0 else NEG

    head = 'white'
    body = _pf_mix('white', 0.16, semantic)
    ax.add_patch(FancyBboxPatch(
        (x, y), size, size, boxstyle='round,pad=0,rounding_size=0.012',
        facecolor=_pf_mix(semantic, 0.10), edgecolor='none', lw=0))

    pad = size * 0.143
    left, right = x + pad, x + size - pad
    top = y + size - pad

    # a position still running under 1 R is called out by an amber ticker, so
    # every tile keeps the same layout and the left edge stays flush. Amber is a
    # weaker foreground on these fills than the white it replaces (2.3:1 against
    # ~5:1), but it separates on hue rather than on value, which is what carries
    # the cue here - and it matches the footnote that explains it.
    warn = not plain and cell['rmul'] < _PF_WARN_R
    ax.text(left, top, cell['ticker'], ha='left', va='top', fontsize=10.5,
            fontweight='bold', color=WARN if warn else head)

    if plain:
        ax.text(left, y + size * (0.42 if is_cash else 0.46),
                '{:,.0f}'.format(cell['value']), ha='left', va='center',
                fontsize=12.5, fontweight='semibold', color=head)
        if is_aggregate:
            ax.text(left, y + pad, 'combined market value', ha='left',
                    va='bottom', fontsize=7.5, color=body)
        return

    ax.text(right, top - size * 0.018, '{} days'.format(cell['days']),
            ha='right', va='top', fontsize=7, color=body)

    # last close and its one-day move
    row_close = y + size * 0.600
    ax.text(left, row_close, '{:,.2f}'.format(cell['close']), ha='left',
            va='center', fontsize=9, color=head)
    change = cell['day_change']
    if change is not None:
        # a move that rounds away is flat, not a signed "-0.0%"
        flat = abs(round(change, 1)) == 0
        label = '0.0%' if flat else _pf_minus('{:+.1f}%'.format(change))
        # red marks a down day, but only where it reads: on a losing (red) tile
        # the fill already carries that, and NEG on NEG is invisible
        down = change < 0 and not flat and semantic != NEG
        ax.text(right, row_close, label, ha='right', va='center', fontsize=8,
                fontweight='bold', color=NEG if down else 'white')

    # what the holding is worth right now
    row_value = y + size * 0.425
    ax.text(left, row_value, 'value', ha='left', va='center', fontsize=7.5,
            color=body)
    ax.text(right, row_value, '{:,.0f}'.format(cell['value']), ha='right',
            va='center', fontsize=9.5, color=head)

    # open profit, in dollars and in R
    ax.plot([left, right], [y + size * 0.300] * 2,
            color=_pf_mix(semantic, 0.45), lw=0.6)
    ax.text(left, y + pad, _pf_minus('{:+,.0f}'.format(cell['gain'])),
            ha='left', va='bottom', fontsize=9.5, fontweight='semibold',
            color=head)
    ax.text(right, y + pad + size * 0.009,
            _pf_minus('{:+.1f}R'.format(cell['rmul'])), ha='right',
            va='bottom', fontsize=8, fontweight='semibold', color=head)


def styled_portfolio_plot(cash, positions, snapshot_date, quote_count, conf, ctx):
    ''' the account's end-of-run composition: a single 0-100% bar splitting the
    equity over the open positions and the cash balance, above a grid of square
    tiles carrying each position's last close, one-day move, market value and
    open profit.

    Returns True when the figure was written. With no position open there is
    nothing to compose - a full-width cash bar and one lone tile - so the figure
    is skipped and the caller leaves it out of the report. '''

    if not positions:
        logger.info("No open positions: skipping the portfolio composition figure")
        return False

    max_tiles = int(conf.get('max_tiles', 16))
    cells = _pf_cells(cash, positions, max_tiles)
    equity = cash + sum(p['value'] for p in positions)
    if equity <= 0:
        logger.warning("Non-positive equity: skipping the portfolio composition figure")
        return False

    rows = -(-len(cells) // _PF_COLS)
    size = (1 - _PF_GAP * (_PF_COLS - 1)) / _PF_COLS
    grid_height = rows * size + (rows - 1) * _PF_GAP

    # lay the figure out in inches so the tiles come out square whatever the row
    # count: the tile axes gets exactly the height its square grid needs, and
    # the surrounding margins stay fixed.
    left, width = 0.035, 0.940
    grid_in = FIG_WIDTH * width * grid_height
    top_margin, bar_in, gap_in, bottom_margin = 0.60, 1.05, 0.15, 0.35
    fig_height = top_margin + bar_in + gap_in + grid_in + bottom_margin

    with report_style():
        fig = plt.figure(figsize=(FIG_WIDTH, fig_height))
        ax_bar = fig.add_axes([left, (bottom_margin + grid_in + gap_in) / fig_height,
                               width, bar_in / fig_height])
        ax_tiles = fig.add_axes([left, bottom_margin / fig_height,
                                 width, grid_in / fig_height])

        fig.text(left, 1 - 0.11 / fig_height,
                 'Portfolio composition and open positions',
                 ha='left', va='top', fontsize=12, fontweight='medium', color=TEXT)
        # how much of the traded universe is actually in play, not just how many
        # positions are open
        held = '{} open position{}'.format(len(positions),
                                           '' if len(positions) == 1 else 's')
        if quote_count:
            # how much of the traded universe is actually in play
            held += ' ({} quotes total)'.format(quote_count)
        fig.text(left, 1 - 0.32 / fig_height,
                 'As at {}  •  equity {:,.0f}  •  {}'.format(
                     snapshot_date, equity, held),
                 ha='left', va='top', fontsize=8, color=TEXT2)

        _pf_bar(ax_bar, cash, positions, equity)

        ax_tiles.set_xlim(0, 1)
        ax_tiles.set_ylim(0, grid_height)
        ax_tiles.axis('off')
        ax_tiles.set_aspect('equal', adjustable='box')
        for i, cell in enumerate(cells):
            row, col = divmod(i, _PF_COLS)
            _pf_tile(ax_tiles, cell, col * (size + _PF_GAP),
                     (rows - 1 - row) * (size + _PF_GAP), size)

        flagged = sum(1 for p in positions if p['rmul'] < _PF_WARN_R)
        if flagged:
            # printed in the same amber as the tickers it explains
            fig.text(left, 0.10 / fig_height,
                     'open gain under {:.0f}R ({} of {})'.format(
                         _PF_WARN_R, flagged, len(positions)),
                     ha='left', va='bottom', fontsize=7.5, fontweight='semibold',
                     color=WARN)

        fig.savefig(ctx.outpath('images', 'portfolio_plot.png'), bbox_inches=None)
        plt.close(fig)

    return True


def styled_trades_plot(trades_lst, Rmul30_lst, ctx):
    ''' each trade in sequence as a lollipop (wins green / losses red), with the
    30-trade rolling R-average line overlaid - the styled take on the classic
    "Trades vs. R-multiple" plot. '''

    R = np.asarray(trades_lst, dtype=float)
    x = np.arange(len(R))
    colors = [POS if v > 0 else NEG for v in R]
    roll = np.asarray(Rmul30_lst, dtype=float)

    with report_style():
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.2))
        ax.vlines(x, 0, R, color=colors, lw=1.0, alpha=0.55)
        ax.scatter(x, R, color=colors, s=14, zorder=3)
        ax.plot(x, roll, color=ACCENT, lw=1.6, alpha=0.9, label='Rmul30 (rolling avg)')
        ax.axhline(0, color=TEXT2, lw=0.8)

        # the rolling average's final value, labelled at the end of the line.
        # Rmul30 is NaN until the 30-trade window fills, so a system with fewer
        # than 30 closed trades has nothing to label.
        valid = np.flatnonzero(np.isfinite(roll))
        if valid.size:
            i = valid[-1]
            # a label centred on a near-zero rolling average lands on top of the
            # y=0 rule, so lift it clear whenever the end value sits close to it
            # (measured against the plotted y-range, not the R value itself)
            ylo, yhi = ax.get_ylim()
            dy = 9 if abs(roll[i]) < 0.06 * (yhi - ylo) else 0
            ax.annotate(f"{roll[i]:+.2f}".replace('-', '−'),
                        (x[i], roll[i]), xytext=(3, dy), textcoords='offset points',
                        va='center', color=ACCENT, fontsize=9, fontweight='medium')

        ax.grid(axis='y'); ax.grid(axis='x', visible=False)
        ax.set_xlabel('Trade')
        ax.set_ylabel('R-multiple')
        # the label goes past the last trade rather than above the line, where a
        # tall neighbouring trade can cross it; the extra x-room keeps it inside
        # the axes instead of widening the figure at savefig(bbox='tight') time
        ax.set_xlim(-1, len(R) + max(2.0, len(R) * 0.05))
        ax.legend(loc='upper left')
        fig.savefig(ctx.outpath('images', 'system_trades_plot.png'))
        plt.close(fig)


def styled_distribution_plot(trades_lst, ctx):
    ''' histogram of trade R-multiples, wins green / losses red. '''

    R = np.asarray(trades_lst, dtype=float)
    wins = R[R > 0]; losses = R[R <= 0]
    lo = float(np.floor(R.min())); hi = float(np.ceil(R.max()))
    bins = np.arange(lo, hi + 1.0, 1.0)

    with report_style():
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.2))
        # rwidth < 1 + white edges give the bars breathing room so they read as
        # distinct bins instead of one solid block
        hist_kw = dict(bins=bins, alpha=0.9, rwidth=0.82, edgecolor='white', linewidth=0.6)
        ax.hist(wins, color=POS, label='Winning trades', **hist_kw)
        ax.hist(losses, color=NEG, label='Losing trades', **hist_kw)
        ax.axvline(0, color=TEXT2, lw=0.8)
        ax.grid(axis='y'); ax.grid(axis='x', visible=False)
        ax.set_xlabel('R-multiple')
        ax.set_ylabel('Number of trades')
        ax.legend(loc='upper right')
        fig.savefig(ctx.outpath('images', 'system_trades_dist_plot.png'))
        plt.close(fig)


def styled_mae_scatter_plot(trades_df, conf, ctx):
    ''' scatter of each closed trade's Maximum Adverse Excursion (MAE, in R)
    against its final R-multiple, wins green / losses red. A research aid for
    choosing the stop distance: read how far winners typically dip against you
    before recovering, versus where the losers sit.

    MAE is censored at 1.0 R by construction, whatever the stloss method: the
    stop always sits exactly 1R below entry (risk_oneR = entry - stoploss), so
    a close past it exits the trade and only a gap through it can land beyond
    1.0. Losers therefore pile up against that wall and the MAE distribution is
    truncated - run a deliberately wide stop to get an uncensored picture.
    Winners are unaffected: a stopped-out trade is a loser, so the winners' MAE
    spread below 1.0 is real. '''

    # completed trades only: the open trailing trade has Exit == "-" and an
    # unrealised outcome, so it is excluded
    closed = trades_df[trades_df['Exit'] != "-"]
    mae = pd.to_numeric(closed['MAE'], errors='coerce')
    rmul = pd.to_numeric(closed['Rmul'], errors='coerce')
    ok = mae.notna() & rmul.notna()
    mae = mae[ok].to_numpy()
    rmul = rmul[ok].to_numpy()
    if mae.size == 0:
        logger.warning("MAE scatter: no closed trades with MAE data - skipping plot")
        return

    win = rmul >= 0   # breakeven counts as a winner, matching the y=0 line

    # keep the 1 R stop band on the axis even if nothing was stopped out
    x_max = max(float(mae.max()) * 1.08, 1.2)

    with report_style():
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.6))
        # shade the stopped-out region (MAE > 1 R), matching the MFE/MAE scatter
        ax.axvspan(1.0, x_max, color=GRID, alpha=0.45, lw=0, zorder=0)
        ax.scatter(mae[win], rmul[win], color=POS, s=16, alpha=0.8, zorder=3,
                   label=f'Winners ({int(win.sum())})')
        ax.scatter(mae[~win], rmul[~win], color=NEG, s=16, alpha=0.8, zorder=3,
                   label=f'Losers ({int((~win).sum())})')
        ax.axhline(0, color=TEXT2, lw=0.8)

        # winners' MAE 95th percentile: marks the tightest stop (in R) that
        # would still have kept ~95% of the winning trades - a candidate stop to
        # read directly against the 1.0 R line. Meaningful for every stloss
        # method in R (in ATR it only was for a percent stop, since the ATR
        # stops drew their own fixed line instead)
        win_mae = mae[win]
        if win_mae.size:
            pv = float(np.percentile(win_mae, 95))
            ax.axvline(pv, color=ACCENT, lw=1.0, ls='--', alpha=0.65)
            ax.text(pv, 0.98, f"Winners P95: {pv:.2f}R ",
                    transform=ax.get_xaxis_transform(), rotation=90,
                    ha='right', va='top', fontsize=8, color=ACCENT)

        # the stop is exactly 1R below entry however stloss computed it, so one
        # reference line serves every method - and it doubles as the censoring
        # wall the losers bunch against
        ax.axvline(1.0, color=NEUTRAL, lw=1.0, ls='--')

        stloss = conf.get('stloss')
        if stloss in ('3atr', '2atr'):
            stop_label = f"Stoploss: {stloss[0]}×ATR (=1R)"
        elif stloss == 'xatr':
            stop_label = f"Stoploss: {float(conf.get('atr_factor', 0)):g}×ATR (=1R)"
        elif stloss == 'percent':
            stop_label = f"Stoploss: {float(conf.get('stoploss', 0)) * 100:.1f}% (=1R)"
        else:
            stop_label = f"Stoploss: {stloss} (=1R)"

        # provenance: the plot is only interpretable against the stop that
        # produced it (a censored tight run and an uncensored wide one look
        # alike otherwise), so name the stop on the chart
        ax.text(0.99, 0.02, stop_label, transform=ax.transAxes,
                ha='right', va='bottom', fontsize=9, color=TEXT2)

        # no in-figure title: the report gives each scatter a styled heading, so
        # a baked-in matplotlib title would just duplicate it
        ax.set_xlabel('Maximum Adverse Excursion (R)')
        ax.set_ylabel('R-multiple')
        ax.set_xlim(-0.02, x_max)
        # extra headroom below the lowest trade so the stop-loss label in the
        # bottom corner always clears the data points
        y_lo, y_hi = float(rmul.min()), float(rmul.max())
        span = max(y_hi - y_lo, 1.0)
        ax.set_ylim(y_lo - 0.20 * span, y_hi + 0.05 * span)
        ax.legend(loc='upper right')
        fig.savefig(ctx.outpath('images', 'mae_scatter_plot.png'))
        plt.close(fig)


# Below this peak a trade had nothing worth keeping, and the kept fraction
# (Rmul / MFE) stops meaning anything: a -1 R stop-out off a 0.05 R peak scores
# -2000%. Those trades are drawn hollow instead of being given a colour that
# would only be ratio noise.
_MIN_PEAK_R = 0.25


def styled_mfe_mae_scatter_plot(trades_df, conf, ctx):
    ''' scatter of each closed trade's two excursions: how far it ran against
    you (MAE, x) against how far it ran for you (MFE, y), both in R, coloured by
    how much of that peak the exit actually kept (Rmul / MFE).

    The colour is the point of the chart. Position alone is largely
    definitional - a winner has MFE >= Rmul > 0 so it is forced up the y axis,
    and every trade past MAE = 1 R was stopped out (the stop sits exactly 1 R
    below entry, whatever the stloss method) so it is a loser by construction;
    the shaded band marks that structural region. What is *not* structural is
    how pale the points are: a trade that peaked at 10 R and closed at 1 R sits
    in the same place as one that closed at 9 R, and only the colour separates
    them. Read the pale and red points at high MFE - those ran well into profit
    and handed it back, which is an exit problem, not an entry one.

    The ramp is clipped at +/-100%: past "gave it all back" the exact negative
    multiple carries nothing and would wash out the rest of the scale. Trades
    peaking below _MIN_PEAK_R are drawn hollow (see above).

    MFE is heavy-tailed, so the y axis is symlog: linear below 1 R, logarithmic
    above. A percent stop in particular makes 1 R a small fixed fraction of
    price, so a long trend can reach 100R+ while the median trade sits near 1 R
    - a linear axis would squash the whole distribution flat to fit the few
    trades that carry the system. The linear stretch below 1 R keeps trades that
    never moved favorably plotted honestly at 0 instead of dropping out as
    log(0). '''

    # completed trades only: the open trailing trade has Exit == "-" and an
    # unrealised outcome, so it is excluded
    closed = trades_df[trades_df['Exit'] != "-"]
    mae = pd.to_numeric(closed['MAE'], errors='coerce')
    mfe = pd.to_numeric(closed['MFE'], errors='coerce')
    rmul = pd.to_numeric(closed['Rmul'], errors='coerce')
    ok = mae.notna() & mfe.notna() & rmul.notna()
    mae = mae[ok].to_numpy()
    mfe = mfe[ok].to_numpy()
    rmul = rmul[ok].to_numpy()
    if mae.size == 0:
        logger.warning("MFE/MAE scatter: no closed trades with excursion data - skipping plot")
        return

    win = rmul >= 0   # same convention as styled_mae_scatter_plot, so the two agree
    has_peak = mfe > _MIN_PEAK_R
    kept = np.full(mfe.shape, np.nan)
    kept[has_peak] = np.clip(rmul[has_peak] / mfe[has_peak], -1.0, 1.0)

    win_kept = kept[has_peak & win]
    med_kept = float(np.median(win_kept)) if win_kept.size else np.nan

    # the stop band always begins at 1 R, so keep it on the axis even in a run
    # where nothing was stopped out
    x_max = max(float(mae.max()) * 1.08, 1.2)
    y_max = max(float(mfe.max()) * 1.6, 2.0)

    with report_style():
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, 4.4))

        ax.axvspan(1.0, x_max, color=GRID, alpha=0.45, lw=0, zorder=0)
        ax.axvline(1.0, color=NEUTRAL, lw=1.1, ls='--', zorder=2)
        ax.axhline(1.0, color=GRID, lw=0.9, zorder=1)

        sc = ax.scatter(mae[has_peak], mfe[has_peak], c=kept[has_peak],
                        cmap=DIVERGING_CMAP, norm=TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1),
                        s=34, alpha=0.95, zorder=3, edgecolors='white', linewidths=0.4)
        if (~has_peak).any():
            ax.scatter(mae[~has_peak], mfe[~has_peak], facecolors='none',
                       edgecolors=TEXT2, s=24, lw=0.7, alpha=0.6, zorder=3)

        ax.set_yscale('symlog', linthresh=1.0, linscale=0.7)
        # 0 and 1 anchor the linear stretch, then one tick per decade of tail
        decades = [10 ** k for k in range(1, int(np.log10(max(y_max, 10))) + 1)]
        ax.set_yticks([0, 1] + decades)
        ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.set_ylim(-0.15, y_max)
        ax.set_xlim(-0.08, x_max)

        # name the shaded region inside its own top corner. Not guaranteed empty
        # - a trade can peak high and still be stopped out later - but in
        # practice stop-outs cluster low, so this is the safest spot for it
        ax.text(1.05, 0.96, 'stop fired  (MAE > 1 R)',
                transform=ax.get_xaxis_transform(), ha='left', va='top',
                fontsize=8, color=TEXT2)

        ax.set_xlabel('Maximum Adverse Excursion (R)')
        ax.set_ylabel('Maximum Favorable Excursion (R)')

        # no in-figure title: the report gives each scatter a styled heading, so
        # a baked-in matplotlib title would just duplicate it

        # win/loss tally and the winners' median capture (ER = share of the peak
        # kept at exit) below the axes: the low-MFE trades run along the bottom
        # of the plot, so there is no in-axes corner wide enough for it. Packed
        # with HPacker so the win/loss colour dots sit inline with the text (a
        # single text artist cannot colour individual glyphs)
        med_str = f"{med_kept:.0%}" if np.isfinite(med_kept) else "n/a"
        tp = dict(color=TEXT2, fontsize=8)

        def _dot(color, rad=3):
            da = DrawingArea(2 * rad, 2 * rad, 0, 0)
            da.add_artist(mpatches.Circle((rad, rad), rad, color=color))
            return da

        row = HPacker(align='center', pad=0, sep=3, children=[
            _dot(POS), TextArea(f"Winners ({int(win.sum())})", textprops=tp),
            _dot(NEG), TextArea(f"Losers ({int((~win).sum())})", textprops=tp),
            TextArea(f"-   Efficiency Ratio: {med_str}", textprops=tp),
        ])
        # anchor below the x-axis label (tick labels + 'MAE (R)' sit above -0.18)
        ax.add_artist(AnchoredOffsetbox(loc='upper left', child=row, pad=0,
                                        borderpad=0, frameon=False,
                                        bbox_to_anchor=(0.0, -0.20),
                                        bbox_transform=ax.transAxes))

        cb = fig.colorbar(sc, ax=ax, pad=0.02, ticks=[-1, -0.5, 0, 0.5, 1])
        cb.ax.set_yticklabels(['≤ −100%', '−50%', '0%', '50%', '100%'], fontsize=7)
        cb.set_label('Efficiency Ratio (ER)', fontsize=8, labelpad=-4)
        cb.outline.set_visible(False)
        cb.ax.tick_params(length=0)

        # winners' median capture marked on the very scale that encodes it
        if np.isfinite(med_kept):
            cb.ax.axhline(med_kept, color=TEXT, lw=1.4)

        fig.savefig(ctx.outpath('images', 'mfe_mae_scatter_plot.png'))
        plt.close(fig)


def styled_montecarlo_plot(mc_result_df, conf, ctx, stats, risk, benchmark,
                           output_filename='monte_carlo_plot.png'):
    ''' Monte Carlo fan chart: a subset of simulated equity paths in the accent
    colour, the median outcome as a solid accent line, and the buy-and-hold
    benchmark as a dashed neutral line. No boxed stat overlay - those numbers
    live in the report's Monte Carlo table. '''

    plot_fraction = conf.get('plot_frac', 0.1)
    n_plot = max(1, int(round(mc_result_df.shape[1] * plot_fraction)))
    plot_cols = np.random.choice(mc_result_df.columns, size=n_plot, replace=False)
    plot_df = mc_result_df[plot_cols]

    x = mc_result_df.index.to_numpy()
    x_first, x_last = x[0], x[-1]
    finals = mc_result_df.iloc[-1]
    median = finals.median()
    p5, p95 = finals.quantile(0.05), finals.quantile(0.95)

    y_max = median + (conf['outlier'] * finals.std())
    if benchmark is not None:
        y_max = max(y_max, benchmark[0] * 1.05)

    pad = 0.09 * (x_last - x_first)
    with report_style():
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.6))
        ax.plot(x, plot_df.to_numpy(), color=ACCENT, lw=0.4, alpha=0.06)
        # small end marker at each plotted path's final value, so the spread of
        # outcomes at the last trade reads as a density of points
        ax.scatter(np.full(plot_df.shape[1], x_last), plot_df.iloc[-1].to_numpy(),
                   color=ACCENT, s=6, alpha=0.15, linewidths=0, zorder=2)
        ax.plot([x_first, x_last], [median, median], color=ACCENT, lw=2.0, label='Median outcome')
        # reference lines end at the last trade (not the padded right edge)
        ax.plot([x_first, x_last], [float(conf['balance'])] * 2, color=NEUTRAL, lw=0.8, ls=':')

        # median value label, left of the endpoint; aligned to the same x as the
        # HODL label below (same negative x offset + right alignment)
        ax.annotate(f"{median:,.0f}", (x_last, median), xytext=(-8, 5),
                    textcoords='offset points', ha='right', va='bottom', color=ACCENT,
                    fontsize=9, fontweight='medium')

        if benchmark is not None:
            val_out, _ = benchmark
            ax.plot([x_first, x_last], [val_out, val_out],
                    color=NEUTRAL, lw=1.6, ls='--', label='Buy & hold')
            ax.annotate(f"{val_out:,.0f}", (x_last, val_out), xytext=(-8, 5),
                        textcoords='offset points', ha='right', va='bottom', color=TEXT2, fontsize=9)

        # 5th / 95th percentile markers, labels at the marker height to their
        # right with the value in brackets (as in the classic plot)
        ax.scatter([x_last, x_last], [p5, p95], color=ACCENT, s=18, zorder=5)
        ax.annotate(f"95% ({p95:,.0f})", (x_last, p95), xytext=(8, 0),
                    textcoords='offset points', ha='left', va='center', color=TEXT2, fontsize=8)
        ax.annotate(f"5% ({p5:,.0f})", (x_last, p5), xytext=(8, 0),
                    textcoords='offset points', ha='left', va='center', color=TEXT2, fontsize=8)

        ax.set_ylim(0, y_max)
        ax.set_xlim(x_first, x_last + pad)
        ax.grid(axis='y'); ax.grid(axis='x', visible=False)
        _thousands(ax)
        ax.set_xlabel('Trade number')
        ax.set_ylabel('Account value (USD)')
        ax.legend(loc='upper left')
        fig.savefig(ctx.outpath('images', output_filename))
        plt.close(fig)


# ---------------------------------------------------------------------------
# Per-ticker price / TA charts - styled counterparts of ticker_plot,
# ticker_plot_ta, ticker_plot_ta_custom and plot_benchmark_price in utils.py.
# These keep the wide monitoring format and all of the information the classic
# charts show; only the visual treatment changes (report palette, muted
# indicator overlays, horizontal hairline grid, %b %Y dates, and the boxed stat
# overlays replaced by plain unboxed text).
# ---------------------------------------------------------------------------

def _ensure_datetime_index(df):
    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)
    return df


def _legend_if_multi(ax, **kw):
    ''' add a legend only when the axis carries 2+ labelled series (report rule);
    single-series panels are named by their y-axis label instead. '''
    if len(ax.get_legend_handles_labels()[1]) > 1:
        ax.legend(**kw)


def _style_price_axis(ax, label='Price (USD)'):
    ''' shared cosmetics for a price panel: horizontal-only hairline grid,
    thousands-separated y axis with no ticks below zero (where a price cannot
    go), larger ticks/label for the wide format. `label` names the currency the
    ticker is quoted in (see RunContext.price_label). '''
    ax.grid(axis='y'); ax.grid(axis='x', visible=False)
    _thousands(ax)
    ax.yaxis.set_major_locator(_NonNegativeLocator())
    ax.set_ylabel(label, fontsize=_AX_FS)
    ax.tick_params(labelsize=_TICK_FS)


def _format_date_axis(ax):
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))


def _active_stoploss_line(ax, df):
    ''' the stoploss level of a still-open trade, as a red dashed line running
    from the day the trade was entered to the last close. Drawn only while a
    position is actually open (InTrade > 0 on the last row); a flat ticker
    carries STLoss 0 and gets no line. '''
    if 'STLoss' not in df.columns or 'InTrade' not in df.columns:
        return

    last = df.iloc[-1]
    if last['InTrade'] <= 0 or last['STLoss'] <= 0:
        return

    # the entry day is the start of the unbroken in-trade run ending at the last
    # row (InTrade is 1 on the ENTER row itself and counts up from there)
    intrade = pd.to_numeric(df['InTrade'], errors='coerce').fillna(0).to_numpy()
    flat = np.flatnonzero(intrade <= 0)
    start = df.index[flat[-1] + 1] if len(flat) else df.index[0]

    ax.hlines(last['STLoss'], start, df.index[-1], colors=NEG, linewidths=1.2,
              linestyles='--', label='Stoploss')

    # the level, printed just past the end of the line (like the last close)
    ax.annotate('{:,.2f}'.format(last['STLoss']),
                xy=(df.index[-1], last['STLoss']), xytext=(6, 0),
                textcoords='offset points', va='center',
                color=NEG, fontsize=_TICK_FS, fontweight='medium')


def _styled_price_overlays(ax, df, conf):
    ''' price-panel overlays (BB / SMA225 / EMA / SMA / Chandelier exits) + Close
    + Enter/Exit markers, styled with the report palette. Muted indicator
    colours, accent Close line, green ^ / red v trade markers. Mirrors the
    classic _plot_price_overlays in utils.py so the two stay in sync. '''
    plot_indicators = conf.get('plot_indicators', [])

    if conf['enter'] == 'BBRSI' or 'BB' in plot_indicators:
        ax.plot(df.index, df[['BBu', 'BBl', 'BBm']], color=NEUTRAL, linewidth=.6)
        ax.fill_between(df.index, df['BBl'], df['BBu'], color=GRID, alpha=.45)

    if 'SMA225' in plot_indicators:
        # 45-week SMA: the bull/bear regime line - allowed to stand out a little
        ax.plot(df.index, df['SMA225'], color=IND_GOLD, linewidth=1.6, linestyle='--', label='SMA225')

    if conf['enter'] == 'DONCH' or 'DON' in plot_indicators:
        ax.plot(df.index, df['DONup'], color=IND_GREEN, linewidth=1.1, linestyle='--', label='DONup')
        ax.plot(df.index, df['DONdn'], color=IND_BROWN, linewidth=1.1, linestyle='--', label='DONdn')
        ax.fill_between(df.index, df['DONdn'], df['DONup'], color=GRID, alpha=.45)

    if conf['enter'] == 'BBB' or conf['exit'] == 'BBB' or 'BBB' in plot_indicators:
        # the entry band and the SMA the exit closes below
        ax.plot(df.index, df['BBBu'], color=IND_GREEN, linewidth=1.1, linestyle='--', label='BBBu')
        ax.plot(df.index, df['BBBm'], color=IND_BROWN, linewidth=1.1, linestyle='--', label=f"SMA{conf['bbb_sma']}")

    if conf['enter'] == '3EMA':
        ax.plot(df.index, df['EMAfast'], color=IND_GREEN, linewidth=1.1, label=f"EMA{conf['ema_fast']}")
        ax.plot(df.index, df['EMAmid'], color=IND_BROWN, linewidth=1.1, label=f"EMA{conf['ema_mid']}")
        ax.plot(df.index, df['EMAslow'], color=IND_CHARCOAL, linewidth=1.1, label=f"EMA{conf['ema_slow']}")

    if conf['enter'] == 'SMA':
        ax.plot(df.index, df['SMAfast'], color=IND_GREEN, linewidth=1.1, label=f"SMA{conf['sma_fast']}")
        ax.plot(df.index, df['SMAslow'], color=IND_BROWN, linewidth=1.1, label=f"SMA{conf['sma_slow']}")

    if conf['exit'] == 'CE':
        ax.plot(df.index, df['CE'], color=IND_CHARCOAL, linewidth=1.0, linestyle='--', label='CEexit')
    if conf['exit'] == 'CEE':
        ax.plot(df.index, df['CE'], color=IND_CHARCOAL, linewidth=1.0, linestyle='--', label='CEexit')
        ax.plot(df.index, df['CE2'], color=IND_BROWN, linewidth=1.0, linestyle='--', label='CE2exit')
        ax.plot(df.index, df['CE15'], color=IND_GOLD, linewidth=1.0, linestyle=':', label='CE15exit')

    _active_stoploss_line(ax, df)

    ax.plot(df.index, df['Close'], color=ACCENT, linewidth=1.4, label='Close')

    if df['Enter'].value_counts().any():
        ax.scatter(df.index, df['Enter'], color=POS, label='Enter', marker='^', s=90, zorder=5)
    if df['Exit'].value_counts().any():
        ax.scatter(df.index, df['Exit'], color=NEG, label='Exit', marker='v', s=90, zorder=5)


def _last_close_labels(ax, df):
    ''' the last close value, printed just past the final point. '''
    close = df.iloc[-1]['Close']
    label = ax.annotate('{:,.2f}'.format(close),
                        xy=(df.index[-1], close), xytext=(6, 0),
                        textcoords='offset points', va='center',
                        color=ACCENT, fontsize=_TICK_FS, fontweight='medium')
    _last_close_change_label(ax, df, label)


def _last_close_change_label(ax, df, label):
    ''' the change between the last close and the one before it, printed right
    after the close label - green when up, red when down. '''
    if len(df) < 2:
        return
    prev, close = df.iloc[-2]['Close'], df.iloc[-1]['Close']
    if not np.isfinite(prev) or not np.isfinite(close) or not prev:
        return
    pct = (close - prev) / prev * 100

    colour = TEXT2
    if pct > 0:
        colour = POS
    elif pct < 0:
        colour = NEG
    ax.annotate('({:+,.1f}%)'.format(pct).replace('-', '−'),
                xy=label.xy, xytext=(6 + _text_width(ax, label) + 4, 0),
                textcoords='offset points', va='center',
                color=colour, fontsize=_TICK_FS, fontweight='medium')


def _text_width(ax, text):
    ''' width of a text object, in points. Measured through the renderer, since a
    text that has not been drawn yet has no window extent. '''
    fig = ax.figure
    get_renderer = getattr(fig.canvas, 'get_renderer', None)
    if get_renderer is None:    # backend without a cached renderer - lay the figure out
        fig.canvas.draw()
        return text.get_window_extent().width * 72 / fig.dpi

    width = get_renderer().get_text_width_height_descent(
        text.get_text(), text.get_fontproperties(), False)[0]
    return width * 72 / fig.dpi


def _eur_values_line(ax, df, eurusd):
    ''' the last close and the active stoploss in EUR, as one line sitting just
    above the legend. Call this after the legend is placed. Nothing is drawn
    without an EUR/USD rate (price_eur off, or a ticker not quoted in USD). '''
    if not eurusd:
        return

    # EURUSD=X quotes USD per EUR, so USD prices divide by the rate
    last = df.iloc[-1]
    parts = ['close €{:,.2f}'.format(last['Close'] / eurusd)]
    if 'STLoss' in df.columns and 'InTrade' in df.columns and last['InTrade'] > 0 and last['STLoss'] > 0:
        parts.append('stoploss €{:,.2f}'.format(last['STLoss'] / eurusd))

    _text_above_legend(ax, '[{}]'.format(', '.join(parts)), fontsize=_TICK_FS, color=TEXT2)


def reserve_bottom_band(ax, frac):
    ''' open up an empty band under the plotted data, `frac` of the data range
    high, so the text that sits along the bottom of a price panel (R-average,
    legend, EUR line) lands in free space instead of on top of the curves.

    Reservations do not stack: the band is always measured against the y range
    as it was before the first call, so a panel that reserves room for both the
    R-average and the EUR line ends up with one band, sized by the larger of the
    two. Prices cannot go negative, but the band regularly reaches under zero on
    a ticker that started near it - _NonNegativeLocator keeps that stretch of
    axis unlabelled. Shared with the classic charts in utils.py. '''
    base = getattr(ax, '_reserved_base_ylim', None)
    if base is None:
        base = ax._reserved_base_ylim = ax.get_ylim()

    frac = max(frac, getattr(ax, '_reserved_frac', 0.0))
    ax._reserved_frac = frac

    bottom, top = base
    ax.set_ylim(bottom - (top - bottom) * frac, top)


def _text_above_legend(ax, text, **kw):
    ''' place a line of text just above the axes' legend, aligned with its left
    edge (bottom right corner of the axes when there is no legend), in a band
    opened up under the data. '''
    ax.figure.canvas.draw()   # the legend only has a position once it is laid out
    x, y, ha = 0.99, 0.02, 'right'
    legend = ax.get_legend()
    if legend is not None:
        try:
            box = legend.get_window_extent().transformed(ax.transAxes.inverted())
            x, y, ha = box.x0, box.y1, 'left'
        except Exception:       # no renderer available - fall back to the corner
            pass

    reserve_bottom_band(ax, _EUR_LINE_BAND)

    ax.annotate(text, xy=(x, y), xycoords='axes fraction', xytext=(0, 8),
                textcoords='offset points', ha=ha, va='bottom', **kw)


def _styled_price_annotations(ax, df):
    ''' the unboxed text callouts on the price panel: last-close value label,
    signal (coloured by outcome), trade-details line, floating date and
    R-average. Same information as the classic ticker_plot annotations, minus
    the boxes. '''
    last = df.iloc[-1]

    _last_close_labels(ax, df)

    # signal, coloured green (bullish / winning) / red (stop / losing) / grey
    signal = last['Signal']
    col, Rstr = TEXT2, ''
    if signal == 'ENTER':
        col = POS
    elif (signal == 'STOPLOSS') or (signal == 'EXIT' and last['Rmul'] <= 0):
        col = NEG
        Rstr = '({:,.1f}R)'.format(last['Rmul'])
    elif signal == 'EXIT':
        col = POS
        Rstr = '({:,.1f}R)'.format(last['Rmul'])
    ax.annotate('Signal: {} {}'.format(signal, Rstr),
                xy=(0.01, 1), xycoords='axes fraction', xytext=(0, -8),
                textcoords='offset points', fontsize=_SIG_FS, fontweight='medium',
                color=col, ha='left', va='top')

    # trade details, second line under the signal
    risk = last['Risk']
    Rmul = last['Profit'] / risk if risk != 0 else 0.0
    ax.annotate('{} days, enter: {:,.2f}, stoploss: {:,.2f}, risk: {:,.2f}, profit: {:,.2f} ({:,.1f}R)'.format(
                    int(last['InTrade']), last['PriceIn'], last['STLoss'], risk, last['Profit'], Rmul),
                xy=(0.01, 1), xycoords='axes fraction', xytext=(0, -32),
                textcoords='offset points', fontsize=_ANN_FS, color=TEXT2, ha='left', va='top')

    # floating date, just above the top-right corner of the panel - outside the
    # axes, so it can't collide with the last-close label when price is trading
    # near the top of the range
    ax.annotate(df.index[-1].strftime('%a %d %b %Y'),
                xy=(0.99, 1), xycoords='axes fraction', xytext=(0, 8),
                textcoords='offset points', fontsize=_ANN_FS, color=TEXT2, ha='right', va='bottom')

    # R-average, bottom-left - in a band opened up under the data, since the
    # left edge of a price panel is normally where the curve runs lowest
    if 'Rmul' in df.columns:
        n = df['Rmul'].count()
        r_avg = df['Rmul'].sum() / n if n else 0.0
        reserve_bottom_band(ax, _R_AVERAGE_BAND)
        ax.annotate('R-average: {:,.2f} ({} trades)'.format(r_avg, n),
                    xy=(0.01, 0.01), xycoords='axes fraction', xytext=(0, 4),
                    textcoords='offset points', fontsize=_ANN_FS, color=TEXT2, ha='left', va='bottom')


def fmt_indicator_value(v):
    ''' compact label for an indicator's latest value: two decimals for the
    bounded oscillators, K/M/B suffixes for the volume-scale ones (OBV, FI). '''
    a = abs(v)
    if a >= 1e9:
        return '{:,.2f}B'.format(v / 1e9)
    if a >= 1e6:
        return '{:,.2f}M'.format(v / 1e6)
    if a >= 1e4:
        return '{:,.1f}K'.format(v / 1e3)
    return '{:,.2f}'.format(v)


def _last_value_labels(ax, df, specs):
    ''' print each series' latest value just past its final point, the way the
    price panel labels the last close. `specs` is a list of (column, colour);
    when a panel carries two series the labels are nudged apart vertically so
    they stay readable where the lines sit close together or cross. '''
    items = []
    for col, color in specs:
        s = df[col].dropna()
        if not s.empty:
            items.append((s.index[-1], float(s.iloc[-1]), color))

    items.sort(key=lambda item: item[1], reverse=True)
    n = len(items)
    for i, (x, v, color) in enumerate(items):
        dy = 0 if n == 1 else ((n - 1) / 2 - i) * 10
        ax.annotate(fmt_indicator_value(v),
                    xy=(x, v), xytext=(6, dy),
                    textcoords='offset points', va='center',
                    color=color, fontsize=_TICK_FS, fontweight='medium')


# series whose latest value is labelled at the right edge of each panel, with
# the colour of the line it belongs to (kept in sync with _indicator_panel)
_PANEL_LAST_VALUES = {
    'RSI': [('RSI', ACCENT)],
    'ADX': [('ADX', ACCENT)],
    'DI': [('P_DI', POS), ('M_DI', NEG)],
    'MACD': [('MACD', ACCENT), ('MACDsig', IND_GOLD)],
    'ATR': [('ATR', ACCENT)],
    'OBV': [('OBV', ACCENT)],
    'FI': [('FI', ACCENT)],
    'CCI': [('CCI', ACCENT)],
    'ROC': [('ROC', ACCENT)],
    'MFI': [('MFI', ACCENT)],
}


def _indicator_panel(ax, df, conf, name):
    ''' draw one named indicator panel (styled). Shared by the styled TA and
    custom-TA charts; mirrors the panel definitions in utils.ticker_plot_ta /
    ticker_plot_ta_custom. '''
    if name == 'RSI':
        ax.plot(df.index, df['RSI'], color=ACCENT, linewidth=1.2, label='RSI')
        ax.axhline(conf['rsi_low'], color=NEUTRAL, linewidth=1.0, linestyle='--')
        ax.axhline(conf['rsi_high'], color=NEUTRAL, linewidth=1.0, linestyle='--')
        ax.fill_between(df.index, conf['rsi_low'], df['RSI'], color=GRID, alpha=.5)
        ax.set_ylabel('RSI', fontsize=_AX_FS)
    elif name == 'ADX':
        ax.plot(df.index, df['ADX'], color=ACCENT, linewidth=1.2, label='ADX')
        ax.axhline(conf['adx_trend'], color=NEUTRAL, linewidth=1.0, linestyle='--')
        ax.set_ylabel('ADX', fontsize=_AX_FS)
    elif name == 'DI':
        ax.plot(df.index, df['P_DI'], color=POS, linewidth=1.2, label='+DI')
        ax.plot(df.index, df['M_DI'], color=NEG, linewidth=1.2, label='−DI')
        ax.set_ylabel('DI', fontsize=_AX_FS)
    elif name == 'MACD':
        hist_colors = np.where(df['MACDhist'] >= 0, POS, NEG)
        ax.bar(df.index, df['MACDhist'], color=hist_colors, width=1, alpha=.6, label='Histogram')
        ax.plot(df.index, df['MACD'], color=ACCENT, linewidth=1.2, label='MACD')
        ax.plot(df.index, df['MACDsig'], color=IND_GOLD, linewidth=1.2, label='Signal')
        ax.axhline(0, color=TEXT2, linewidth=0.8)
        ax.set_ylabel('MACD', fontsize=_AX_FS)
    elif name == 'ATR':
        ax.plot(df.index, df['ATR'], color=ACCENT, linewidth=1.2, label='ATR')
        ax.set_ylabel('ATR', fontsize=_AX_FS)
    elif name == 'OBV':
        ax.plot(df.index, df['OBV'], color=ACCENT, linewidth=1.2, label='OBV')
        ax.set_ylabel('OBV', fontsize=_AX_FS)
    elif name == 'FI':
        ax.plot(df.index, df['FI'], color=ACCENT, linewidth=1.2, label='FI')
        ax.axhline(0, color=TEXT2, linewidth=0.8)
        ax.set_ylabel('FI', fontsize=_AX_FS)
    elif name == 'CCI':
        ax.plot(df.index, df['CCI'], color=ACCENT, linewidth=1.2, label='CCI')
        ax.axhline(100, color=NEUTRAL, linewidth=1.0, linestyle='--')
        ax.axhline(-100, color=NEUTRAL, linewidth=1.0, linestyle='--')
        ax.set_ylabel('CCI', fontsize=_AX_FS)
    elif name == 'ROC':
        ax.plot(df.index, df['ROC'], color=ACCENT, linewidth=1.2, label='ROC')
        ax.axhline(0, color=TEXT2, linewidth=0.8)
        ax.set_ylabel('ROC', fontsize=_AX_FS)
    elif name == 'MFI':
        ax.plot(df.index, df['MFI'], color=ACCENT, linewidth=1.2, label='MFI')
        ax.axhline(80, color=NEUTRAL, linewidth=1.0, linestyle='--')
        ax.axhline(20, color=NEUTRAL, linewidth=1.0, linestyle='--')
        ax.set_ylabel('MFI', fontsize=_AX_FS)

    _last_value_labels(ax, df, _PANEL_LAST_VALUES.get(name, []))

    ax.grid(axis='y'); ax.grid(axis='x', visible=False)
    ax.tick_params(labelsize=_TICK_FS)
    _legend_if_multi(ax, loc='upper left', fontsize=_LEG_FS)


def styled_ticker_plot(df, ticker, description, conf, ctx):
    ''' styled counterpart of utils.ticker_plot: price + overlays + enter/exit. '''
    df = _ensure_datetime_index(df)
    with report_style():
        fig, ax = plt.subplots(figsize=(28, 10))
        fig.suptitle('{} ({})'.format(description, ticker), fontsize=_TITLE_FS, fontweight='medium')
        _styled_price_overlays(ax, df, conf)
        _styled_price_annotations(ax, df)
        _style_price_axis(ax, ctx.price_label(ticker))
        _format_date_axis(ax)
        _legend_if_multi(ax, loc='lower right', ncol=3, fontsize=_LEG_FS)
        _eur_values_line(ax, df, ctx.eur_rate(ticker))
        fig.savefig(ctx.outpath('plots', f'{ticker}_plot.png'))
        plt.close(fig)


def _styled_ta_figure(df, ticker, description, conf, ctx, panels, out_dir, out_file):
    ''' price panel (3x height) + one styled indicator panel per entry in
    `panels`, stacked and sharing the x axis. Shared by styled_ticker_plot_ta
    (panels derived from the strategy) and styled_ticker_plot_ta_custom. '''
    df = _ensure_datetime_index(df)
    n = len(panels)
    with report_style():
        fig, axes = plt.subplots(n + 1, 1, sharex=True, figsize=(28, 5 * (n + 1)),
                                 gridspec_kw={'height_ratios': [3] + [1] * n})
        axes = np.atleast_1d(axes)
        fig.suptitle('{} ({})'.format(description, ticker), fontsize=_TITLE_FS, fontweight='medium')

        ax1 = axes[0]
        _styled_price_overlays(ax1, df, conf)
        _styled_price_annotations(ax1, df)
        _style_price_axis(ax1, ctx.price_label(ticker))
        _legend_if_multi(ax1, loc='lower right', ncol=3, fontsize=_LEG_FS)
        _eur_values_line(ax1, df, ctx.eur_rate(ticker))

        for ax, name in zip(axes[1:], panels):
            _indicator_panel(ax, df, conf, name)

        _format_date_axis(axes[-1])
        fig.savefig(ctx.outpath(out_dir, out_file))
        plt.close(fig)


def styled_ticker_plot_ta(df, ticker, description, conf, ctx):
    ''' styled counterpart of utils.ticker_plot_ta: price panel + the strategy's
    indicator panels (RSI for BBRSI/RSI, MACD for MACD, ATR + ADX for DONCH/BBB, else
    ADX + directional indicators). '''
    if conf['enter'] == 'BBRSI' or conf['enter'] == 'RSI':
        panels = ['RSI']
    elif conf['enter'] == 'MACD':
        panels = ['MACD']
    elif conf['enter'] in ('DONCH', 'BBB'):
        panels = ['ATR', 'ADX']
    else:
        panels = ['ADX', 'DI']
    _styled_ta_figure(df, ticker, description, conf, ctx, panels,
                      'plots/TA', f'{ticker}_plot_ta.png')


def styled_ticker_plot_ta_custom(df, ticker, description, conf, ctx):
    ''' styled counterpart of utils.ticker_plot_ta_custom: price panel + one
    panel per conf['ta_custom'] indicator. '''
    _styled_ta_figure(df, ticker, description, conf, ctx, list(conf['ta_custom']),
                      'plots/TA-custom', f'{ticker}_plot_ta_custom.png')


def styled_benchmark_price(df, ticker, description, conf, ctx):
    ''' styled counterpart of utils.plot_benchmark_price: a plain Close-price
    chart (no trading signals) with the configured plot_indicators overlay, used
    for the auto-injected benchmark ticker and for follow_only mode. '''
    df = _ensure_datetime_index(df)
    plot_indicators = conf.get('plot_indicators', [])

    with report_style():
        fig, ax = plt.subplots(figsize=(28, 10))
        fig.suptitle('{} ({})'.format(description, ticker), fontsize=_TITLE_FS, fontweight='medium')

        if 'BB' in plot_indicators:
            # reuse precomputed Bollinger columns when present (follow_only), else
            # compute here (the auto-injected benchmark is charted from raw OHLC)
            if 'BBu' in df.columns:
                bbu, bbm, bbl = df['BBu'], df['BBm'], df['BBl']
            else:
                bbu, bbm, bbl = ta.BBANDS(df['Close'], timeperiod=20, matype=0)
            ax.plot(df.index, bbu, color=NEUTRAL, linewidth=.6)
            ax.plot(df.index, bbm, color=NEUTRAL, linewidth=.6)
            ax.plot(df.index, bbl, color=NEUTRAL, linewidth=.6)
            ax.fill_between(df.index, bbl, bbu, color=GRID, alpha=.45)

        if 'SMA225' in plot_indicators:
            sma225 = df['SMA225'] if 'SMA225' in df.columns else ta.SMA(df['Close'], timeperiod=225)
            ax.plot(df.index, sma225, color=IND_GOLD, linewidth=1.6, linestyle='--', label='SMA225')

        if 'DON' in plot_indicators:
            donup = df['DONup'] if 'DONup' in df.columns else df['High'].rolling(conf['donch_enter']).max().shift(1)
            dondn = df['DONdn'] if 'DONdn' in df.columns else df['Low'].rolling(conf['donch_exit']).min().shift(1)
            ax.plot(df.index, donup, color=IND_GREEN, linewidth=1.1, linestyle='--', label='DONup')
            ax.plot(df.index, dondn, color=IND_BROWN, linewidth=1.1, linestyle='--', label='DONdn')
            ax.fill_between(df.index, dondn, donup, color=GRID, alpha=.45)

        if 'BBB' in plot_indicators:
            if 'BBBu' in df.columns:
                bbbu, bbbm = df['BBBu'], df['BBBm']
            else:
                bbbu, bbbm, _ = ta.BBANDS(df['Close'], timeperiod=conf['bbb_sma'],
                    nbdevup=conf['bbb_std'], nbdevdn=conf['bbb_std'], matype=0)
            ax.plot(df.index, bbbu, color=IND_GREEN, linewidth=1.1, linestyle='--', label='BBBu')
            ax.plot(df.index, bbbm, color=IND_BROWN, linewidth=1.1, linestyle='--', label=f"SMA{conf['bbb_sma']}")

        ax.plot(df.index, df['Close'], color=ACCENT, linewidth=1.4, label='Close')
        _last_close_labels(ax, df)

        _style_price_axis(ax, ctx.price_label(ticker))
        _format_date_axis(ax)
        _legend_if_multi(ax, loc='lower right', fontsize=_LEG_FS)
        _eur_values_line(ax, df, ctx.eur_rate(ticker))
        fig.savefig(ctx.outpath('plots', f'{ticker}_plot.png'))
        plt.close(fig)
