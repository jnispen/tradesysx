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
from matplotlib.ticker import StrMethodFormatter

from tradesysx.report_style import (report_style, ACCENT, NEUTRAL, POS, NEG, GRID, TEXT2,
                                    IND_GREEN, IND_BROWN, IND_CHARCOAL, IND_GOLD,
                                    FIG_WIDTH)

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
    title-case of the raw key for any method not in the map. '''
    key = conf.get('pos_sizing', '')
    return _POS_SIZING_LABELS.get(key, key.replace('_', ' ').capitalize())


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


def _style_price_axis(ax):
    ''' shared cosmetics for a price panel: horizontal-only hairline grid,
    thousands-separated y axis, larger ticks/label for the wide format. '''
    ax.grid(axis='y'); ax.grid(axis='x', visible=False)
    _thousands(ax)
    ax.set_ylabel('Price (USD)', fontsize=_AX_FS)
    ax.tick_params(labelsize=_TICK_FS)


def _format_date_axis(ax):
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))


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

    if conf['enter'] == '3EMA':
        ax.plot(df.index, df['EMA20'], color=IND_GREEN, linewidth=1.1, label='EMA20')
        ax.plot(df.index, df['EMA50'], color=IND_BROWN, linewidth=1.1, label='EMA50')
        ax.plot(df.index, df['EMA100'], color=IND_CHARCOAL, linewidth=1.1, label='EMA100')

    if conf['enter'] == 'SMA':
        ax.plot(df.index, df['SMAfast'], color=IND_GREEN, linewidth=1.1, label=f"SMA{conf['sma_fast']}")
        ax.plot(df.index, df['SMAslow'], color=IND_BROWN, linewidth=1.1, label=f"SMA{conf['sma_slow']}")

    if conf['exit'] == 'CE':
        ax.plot(df.index, df['CE'], color=IND_CHARCOAL, linewidth=1.0, linestyle='--', label='CEexit')
    if conf['exit'] == 'CEE':
        ax.plot(df.index, df['CE'], color=IND_CHARCOAL, linewidth=1.0, linestyle='--', label='CEexit')
        ax.plot(df.index, df['CE2'], color=IND_BROWN, linewidth=1.0, linestyle='--', label='CE2exit')
        ax.plot(df.index, df['CE15'], color=IND_GOLD, linewidth=1.0, linestyle=':', label='CE15exit')

    ax.plot(df.index, df['Close'], color=ACCENT, linewidth=1.4, label='Close')

    if df['Enter'].value_counts().any():
        ax.scatter(df.index, df['Enter'], color=POS, label='Enter', marker='^', s=90, zorder=5)
    if df['Exit'].value_counts().any():
        ax.scatter(df.index, df['Exit'], color=NEG, label='Exit', marker='v', s=90, zorder=5)


def _styled_price_annotations(ax, df):
    ''' the unboxed text callouts on the price panel: last-close value label,
    signal (coloured by outcome), trade-details line, floating date and
    R-average. Same information as the classic ticker_plot annotations, minus
    the boxes. '''
    last = df.iloc[-1]

    # last close value, printed just past the final point
    ax.annotate('{:,.2f}'.format(last['Close']),
                xy=(df.index[-1], last['Close']), xytext=(6, 0),
                textcoords='offset points', va='center',
                color=ACCENT, fontsize=_TICK_FS, fontweight='medium')

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

    # floating date, top-right
    ax.annotate(df.index[-1].strftime('%a %d %b %Y'),
                xy=(0.99, 1), xycoords='axes fraction', xytext=(0, -8),
                textcoords='offset points', fontsize=_ANN_FS, color=TEXT2, ha='right', va='top')

    # R-average, bottom-left
    if 'Rmul' in df.columns:
        n = df['Rmul'].count()
        r_avg = df['Rmul'].sum() / n if n else 0.0
        ax.annotate('R-average: {:,.2f} ({} trades)'.format(r_avg, n),
                    xy=(0.01, 0.01), xycoords='axes fraction', xytext=(0, 4),
                    textcoords='offset points', fontsize=_ANN_FS, color=TEXT2, ha='left', va='bottom')


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
        _style_price_axis(ax)
        _format_date_axis(ax)
        _legend_if_multi(ax, loc='lower right', ncol=3, fontsize=_LEG_FS)
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
        _style_price_axis(ax1)
        _legend_if_multi(ax1, loc='lower right', ncol=3, fontsize=_LEG_FS)

        for ax, name in zip(axes[1:], panels):
            _indicator_panel(ax, df, conf, name)

        _format_date_axis(axes[-1])
        fig.savefig(ctx.outpath(out_dir, out_file))
        plt.close(fig)


def styled_ticker_plot_ta(df, ticker, description, conf, ctx):
    ''' styled counterpart of utils.ticker_plot_ta: price panel + the strategy's
    indicator panels (RSI for BBRSI, MACD for MACD, else ADX + directional
    indicators). '''
    if conf['enter'] == 'BBRSI':
        panels = ['RSI']
    elif conf['enter'] == 'MACD':
        panels = ['MACD']
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

        ax.plot(df.index, df['Close'], color=ACCENT, linewidth=1.4, label='Close')
        ax.annotate('{:,.2f}'.format(df.iloc[-1]['Close']),
                    xy=(df.index[-1], df.iloc[-1]['Close']), xytext=(6, 0),
                    textcoords='offset points', va='center',
                    color=ACCENT, fontsize=_TICK_FS, fontweight='medium')

        _style_price_axis(ax)
        _format_date_axis(ax)
        _legend_if_multi(ax, loc='lower right', fontsize=_LEG_FS)
        fig.savefig(ctx.outpath('plots', f'{ticker}_plot.png'))
        plt.close(fig)
