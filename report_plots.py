''' Styled system-level report charts (used when report_style="styled").

These are the redesigned versions of the equity/balance, trades, trade
distribution and Monte Carlo charts, following the report-styling palette and
rules (no boxed stat overlays inside the axes, wins green / losses red, equity
in the accent colour, benchmark as a dashed neutral reference line, thousands
separators on money axes). Each function saves a PNG to the same path its
classic counterpart uses, so the rest of the pipeline is unaffected; the
styled summary report then embeds those PNGs.

All plotting runs inside `report_style()` so the styling is scoped to these
charts only and the per-ticker / TA plots stay untouched. '''

import logging

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import StrMethodFormatter

from tradesysx.report_style import report_style, ACCENT, NEUTRAL, POS, NEG, TEXT2, FIG_WIDTH

logger = logging.getLogger(__name__)


def _thousands(ax):
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))


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
        ax.grid(axis='y'); ax.grid(axis='x', visible=False)
        ax.set_xlabel('Trade')
        ax.set_ylabel('R-multiple')
        ax.set_xlim(-1, len(R))
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
