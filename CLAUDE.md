# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commit messages

Use a one-line commit message and do not add a `Co-Authored-By` trailer.

## What this is

GetQuotes is a backtesting and paper-trading toolkit for mechanical trading systems, inspired by Van K. Tharp's trading systems books. It downloads historical OHLC data (yfinance), applies a configurable entry/exit/stoploss strategy, simulates a trading account, and runs Monte Carlo analysis on the resulting trades. See README.md for the full stepwise pipeline description.

## Commands

```sh
pip install -r requirements.txt
```

`TA-Lib` requires the underlying TA-Lib C library to be installed separately before the Python bindings can be built.

Run the main pipeline:

```sh
python getquotes.py [--basedir <path>]
```

Run the standalone Monte Carlo simulator:

```sh
python tst/simulator.py [--basedir <path>]
```

`--basedir` defaults to the current working directory and is used to locate `config/`, `quotes/` and `out/`. There is no test suite, linter, or build step in this repo.

To check whether `requirements.txt` is sufficient on its own, build a throwaway venv from it, import every module, then run the full pipeline against a minimal one-ticker config (to limit yfinance calls):

```sh
python3 -m venv /tmp/venv_test && /tmp/venv_test/bin/pip install -r requirements.txt
/tmp/venv_test/bin/python -c "import utils, context, strategy, tables"

mkdir -p /tmp/run_test/config /tmp/run_test/quotes
cp config/system_conf.json /tmp/run_test/config/
echo '{"AAPL": "Apple Inc."}' > /tmp/run_test/quotes/quotes_stocks.lst
/tmp/venv_test/bin/python getquotes.py --basedir /tmp/run_test
```

The import check doesn't cover runtime issues like yfinance network calls, WeasyPrint's system deps (Pango/Cairo), the TA-Lib C library (installed separately), or version-dependent breakage. Example of the latter: `requirements.txt` pins no `pandas` version, so it can resolve to pandas 3.x, which removed the implicit single-element-`Series`→scalar conversion via `float()`/`int()` (previously a `FutureWarning`, now a hard `TypeError`). Any `float(df['col'])`/`int(df['col'])` on a one-row selection must be `float(df['col'].iloc[0])` instead — fixed for this reason in the "close open trades" branch of `do_balance_simulation` in `utils.py`.

## Architecture

### Pipeline entry point — `getquotes.py`

`main()` builds a `RunContext`, loads `config/system_conf.json` (and `config/telegram_conf.json` if `notify` is true), then calls `update_quotes(conf, ctx)`. `update_quotes` loops over every ticker in the configured quotes file (`config/quotes_stocks.lst`-style JSON, e.g. `quotes/quotes_stocks.lst`) and runs the per-ticker pipeline: download/read OHLC → add TA indicators → generate ENTER/EXIT signals → plot → build trades table/list. After the loop it runs the system-wide steps: save trades table, compute system stats, run the balance simulation, run the Monte Carlo simulation, and generate the combined PDF report. Optionally sends a Telegram notification.

### Shared state — `context.py`

Two dataclasses are threaded explicitly through function signatures instead of using a global/mutable config module:
- `RunContext` — `basedir`, telegram `bot_token`/`chat_id`, and `.path(*parts)` which joins onto `basedir` and creates parent directories (replaces the old `data_path()` helper / `config.basedir`).
- `SystemStats` — pipeline statistics (`sqn`, `kelly_crit`, `trades_len`, `trades_num`, `win_rate`, `avg_risk`, `min_balance`, `max_drawdown`) that are computed by one pipeline stage and consumed by a later one (e.g. `generate_system_stats` sets `sqn`/`kelly_crit`/`win_rate`, `do_balance_simulation` sets `avg_risk`, the Monte Carlo step sets `min_balance`/`max_drawdown`).

Almost every function in `utils.py` takes `(conf, ctx)` or `(conf, ctx, stats)` — `conf` is the plain dict loaded from `system_conf.json`, `ctx`/`stats` are the dataclasses above.

### Core logic — `utils.py`

Single large module containing the whole pipeline implementation, roughly in pipeline order:
- Data download (`get_quotes_data`, `get_history_data` via yfinance), Telegram helpers (`bot_signal_update`, `bot_summary_update`).
- TA indicators (`add_technical_indicators`, via TA-Lib): RSI, ATR, ADX, ±DI, SMA/EMA, Bollinger Bands, Chandelier Exit.
- Signal generation (`add_trading_signals`): a stateful per-row walk through each ticker's price history applying the configured enter/exit/stoploss strategy (see `strategy.py`), tracking `intrade`, MAE/MFE/E-Ratio, R-multiples. Writes results via pre-allocated lists assigned to columns once at the end (not per-cell `.at` writes).
- Trades table/list construction (`generate_trading_table`) — vectorized extraction of ENTER/EXIT events via boolean masks, pairing each EXIT positionally with its preceding ENTER.
- System statistics (`generate_system_stats`): SQN, Kelly criterion, win rate, R-multiple stats, plus `trades_plot`.
- Position sizing (`compute_position_size`): `core_equity_risk`, `fixed_dollar_risk`, `fixed_ratio`, `fixed_amount`, `kelly` — selected by `conf['pos_sizing']`.
- Balance simulation (`do_balance_simulation`): paper-trades the signals using the configured position sizing, tracks account balance/value over time. Pre-loads each ticker's OHLC CSV once via `load_ohlc_cache` (used by `get_total_invested_value`) rather than re-reading per row.
- Monte Carlo simulation: `do_monte_carlo_simulation_sampled` → `run_monte_carlo_sampled` resamples the R-multiple distribution ("bag of marbles"); the per-trade balance update (`balance *= 1 + risk*Rmul`) is vectorized with `np.cumprod`. `do_monte_carlo_simulation_shuffled`/`plot_monte_carlo_results_shuffled` (permutation-based variant) exist but are currently unused/commented out in `getquotes.py`.
- Reporting: `generate_summary_report` builds the combined `out/system_summary.pdf` via WeasyPrint; `df_to_html` is the shared table→HTML/CSS helper for the PDF tables.
- Plotting: `ticker_plot`, `ticker_plot_ta`, `balance_plot`, `trades_plot`, plus the Monte Carlo plot functions — all save PNGs under `ctx.path("out/...")`.

### Strategies — `strategy.py`

- `Stoploss` — `3atr` (3×ATR below close) or `percent`, selected via `conf['stloss']`.
- `TradingSignals` — enter strategies (`3EMA`, `SMA`, `BBRSI`) and exit strategies (`CE`, `CEE`, `RSI`, `XR`, `3EMA`, `SMA`, `BBRSI`), selected via `conf['enter']`/`conf['exit']`. `CEE`/`XR` exit checks read `row['Rcur']`, which is initialized to `NaN` before the signal loop in `add_trading_signals` and reflects the pre-iteration snapshot (not the value computed earlier in the same row) — this is existing, intentional-ish behavior, don't "fix" it without checking with the user.

### `tables.py`

Trivial wrapper classes (`TotalTradesList`, `TradesTable`) — each just holds a `self.df` DataFrame with a fixed column set, used as typed containers passed between `utils.py` functions.

### `tst/simulator.py` — intentionally separate

A standalone Monte Carlo tool, living in its own `tst/` directory with its own `tst/config/simulator_conf.json` and [tst/README.md](tst/README.md). It still uses the old global `config` namespace-package pattern (`import config`, `config.basedir`, `config.sqn`, etc., resolved via the sibling `tst/config/` namespace package) and has its own duplicated copies of `do_monte_carlo_simulation`/`plot_monte_carlo_results_sampled`/`data_path`. This divergence from `getquotes.py`/`utils.py` (which use `RunContext`/`SystemStats`) is **intentional** — don't refactor it to share code with `utils.py` unless asked.

### Configuration (`config/`)

- `system_conf.json` — main config: data range, indicator periods, strategy selection (`enter`/`exit`/`stloss`), position sizing, account balance/risk, Monte Carlo params (`iterations`, `sim_len_max`, `outlier`).
- `telegram_conf.json` — bot token/chat ID, only read when `notify` is true.
- `tst/config/simulator_conf.json` — config for the standalone `tst/simulator.py`.
- `quotes/quotes_stocks.lst` — JSON dict of `{ticker: description}`; `update_quotes` injects an extra `"URTH"` (MSCI World) entry as the buy-and-hold benchmark.

### Output (`out/`, gitignored)

`out/data/` (raw + processed OHLC per ticker), `out/plots/` (+ `out/plots/TA/`), `out/reports/` (system-level plots), `out/tables/` (trades CSVs), and combined PDFs at `out/system_summary.pdf`, `out/trades_table.pdf`, `out/trades_list.pdf`.
