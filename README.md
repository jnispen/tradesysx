### GetQuotes

GetQuotes is a backtesting and paper-trading toolkit for mechanical
trading systems. It downloads historical stock data, applies a configurable
entry/exit/stoploss strategy, simulates a trading account, and runs a Monte
Carlo analysis on the resulting trades.

The toolkit was directly inspired by the various books on trading systems
development written by Dr. Van K. Tharp (<https://vantharpinstitute.com/>).

#### How it works

Running `getquotes.py` performs the following steps for every ticker in the
configured quotes file:

1. **Download data** — fetch daily OHLC price history from Yahoo Finance
   (`yfinance`) and store it as `<outdir>/data/<TICKER>_ohlc_raw.csv`.
2. **Add technical indicators** — compute RSI, ATR, ADX, ±DI, SMA/EMA
   moving averages, Bollinger Bands and Chandelier Exit levels (`TA-Lib`).
3. **Generate ENTER/EXIT signals** — apply the configured entry strategy
   (`3EMA`, `SMA` or `BBRSI`), exit strategy (`CE`, `CEE`, `RSI`, `XR`,
   `3EMA`, `SMA` or `BBRSI`) and stoploss method (`3atr` or `percent`) to
   produce per-day trading signals.
4. **Plot ticker charts** — save a price/indicator chart per ticker
   (`<outdir>/plots/`), optionally with a separate technical-analysis panel
   (`<outdir>/plots/TA/`).
5. **Build the trades table** — collect every completed (and any still-open)
   trade into a combined trades table and trades list, including R-multiples,
   MAE/MFE and E-Ratio.
6. **Compute system statistics** — System Quality Number (SQN), win rate,
   Kelly criterion, average R per win/loss, trades/year, etc.
7. **Run the balance simulation** — paper-trade the signals using the
   configured position sizing strategy (`core_equity_risk`,
   `fixed_dollar_risk`, `fixed_ratio`, `fixed_amount` or `kelly`) and track
   the account balance over time.
8. **Run a Monte Carlo simulation** — resample the R-multiple distribution
   from the trades to estimate the range of possible outcomes, drawdown and
   loss streaks, and compare against a buy-and-hold benchmark (MSCI World /
   URTH).
9. **Generate reports** — save all plots, tables (CSV/PDF) and a combined
   `<outdir>/system_summary.pdf` report covering configuration, statistics and
   charts.
10. **Notify via Telegram** *(optional)* — post the daily ENTER/EXIT/stoploss
    signals and the summary PDF to a configured Telegram chat.

#### Ticker plot indicators

The price chart (`<outdir>/plots/<TICKER>_plot.png`) and the price panel of
the TA chart (`<outdir>/plots/TA/<TICKER>_plot_ta.png`) always show the same
overlays, picked from three tiers:

- **Fixed** — the close price, ENTER/EXIT markers and trade annotations are
  always shown.
- **Strategy-driven** — an indicator set is shown automatically when it
  matches the configured `enter` strategy: EMA20/50/100 for `3EMA`, the
  fast/slow SMA pair for `SMA`, Bollinger Bands for `BBRSI`. The Chandelier
  Exit levels are likewise shown automatically based on the `exit` strategy
  (`CE` or `CEE`). These aren't configurable — they follow whatever
  `enter`/`exit` is set to.
- **User-selectable** — the `plot_indicators` list in `system_conf.json` adds
  indicators that aren't tied to a strategy, currently `"BB"` (Bollinger
  Bands) and `"SMA225"` (225-day SMA, a simple bull/bear market reference).
  An empty or missing list shows none of these. An unrecognized name causes
  the pipeline to exit with an error before any data is processed.

#### Configuration

All behaviour is controlled via JSON config files in `config/`:

- `config/system_conf.json` — main configuration: data range, indicator
  settings, strategy selection (enter/exit/stoploss), position sizing,
  account balance, risk per trade, Monte Carlo parameters, and the
  `ta_custom` panel list used by `--custom-ta`.
- `config/telegram_conf.json` — bot token and chat ID, only required when
  `notify` is `true`.
- `quotes/quotes_stocks.lst` — the list of tickers (with descriptions) to
  process.

#### Setup

1. Install Python dependencies:

   ```sh
   pip install -r requirements.txt
   ```

   Note: `TA-Lib` requires the underlying TA-Lib C library to be installed
   separately before the Python bindings can be built.
2. Adjust `config/system_conf.json` (and `quotes/quotes_stocks.lst`) to match
   your desired tickers, strategy and account settings.
3. (Optional) Fill in `config/telegram_conf.json` and set `"notify": true` to
   receive daily updates on Telegram.
4. Run the pipeline:

   ```sh
   python getquotes.py [--basedir <path>] [--config <file>] [--outdir <path>] [--report <summary|full>] [--custom-ta] [--loglevel <level>]
   ```

   `--basedir` defaults to the current working directory and is used to
   locate the `config/` and `quotes/` directories.

   `--config` selects the system configuration file. Relative paths are
   resolved against `basedir`; absolute paths are used as-is. Defaults to
   `config/system_conf.json`.

   `--outdir` sets the output directory where all generated data, plots,
   tables and reports are written. Relative paths are resolved against
   `basedir`; absolute paths are used as-is. Defaults to `out`.

   `--report` selects the summary report type: `summary` (default) writes
   `<outdir>/system_summary.pdf` with the system-level figures only; `full`
   additionally appends every ticker's plot and writes
   `<outdir>/full_system_summary.pdf` instead.

   `--loglevel` controls console verbosity and accepts `DEBUG`, `INFO`
   (default), `WARNING`, `ERROR` or `CRITICAL`. `INFO` shows section banners,
   per-ticker progress and final summaries; `DEBUG` additionally shows
   per-trade details and full configuration/table dumps. The same flag is
   available on `tst/simulator.py` (see [tst/README.md](tst/README.md)).

   `--custom-ta` is off by default and generates an extra ad-hoc diagnostic
   plot per ticker (`<outdir>/plots/TA-custom/<TICKER>_plot_ta_custom.png`):
   the price panel plus one stacked panel per entry in the `ta_custom` list
   in `system_conf.json` (valid entries: `RSI`, `ADX`, `DI`, `MACD`, `ATR`,
   `OBV`, `FI`). Passing `--custom-ta` with an empty or missing `ta_custom`
   list is an error.

#### Output

All generated data, plots, tables and reports are written under the output
directory (default `out/`, configurable via `--outdir`):

- `<outdir>/data/` — raw and processed OHLC data per ticker
- `<outdir>/plots/` — per-ticker price charts (`<outdir>/plots/TA/` for
  indicator panels, and `<outdir>/plots/TA-custom/` when `--custom-ta` is
  passed)
- `<outdir>/images/` — system-level plots (trades distribution, balance,
  Monte Carlo)
- `<outdir>/tables/` — trades table and trades list as CSV
- `<outdir>/system_summary.pdf` (or `<outdir>/full_system_summary.pdf` with
  `--report full`), `<outdir>/trades_table.pdf`, `<outdir>/trades_list.pdf` —
  combined PDF reports
