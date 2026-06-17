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

#### Configuration

All behaviour is controlled via JSON config files in `config/`:

- `config/system_conf.json` — main configuration: data range, indicator
  settings, strategy selection (enter/exit/stoploss), position sizing,
  account balance, risk per trade, and Monte Carlo parameters.
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
   python getquotes.py [--basedir <path>] [--config <file>] [--outdir <path>] [--loglevel <level>]
   ```

   `--basedir` defaults to the current working directory and is used to
   locate the `config/` and `quotes/` directories.

   `--config` selects the system configuration file. Relative paths are
   resolved against `basedir`; absolute paths are used as-is. Defaults to
   `config/system_conf.json`.

   `--outdir` sets the output directory where all generated data, plots,
   tables and reports are written. Relative paths are resolved against
   `basedir`; absolute paths are used as-is. Defaults to `out`.

   `--loglevel` controls console verbosity and accepts `DEBUG`, `INFO`
   (default), `WARNING`, `ERROR` or `CRITICAL`. `INFO` shows section banners,
   per-ticker progress and final summaries; `DEBUG` additionally shows
   per-trade details and full configuration/table dumps. The same flag is
   available on `tst/simulator.py` (see [tst/README.md](tst/README.md)).

#### Output

All generated data, plots, tables and reports are written under the output
directory (default `out/`, configurable via `--outdir`):

- `<outdir>/data/` — raw and processed OHLC data per ticker
- `<outdir>/plots/` — per-ticker price charts (and `<outdir>/plots/TA/` for
  indicator panels)
- `<outdir>/reports/` — system-level plots (trades distribution, balance,
  Monte Carlo)
- `<outdir>/tables/` — trades table and trades list as CSV
- `<outdir>/system_summary.pdf`, `<outdir>/trades_table.pdf`,
  `<outdir>/trades_list.pdf` — combined PDF reports
