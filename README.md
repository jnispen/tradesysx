# GetQuotes (backtesting trading systems)

GetQuotes is a backtesting toolkit for mechanical trading systems. It downloads historical OHLC stock data
from [Yahoo Finance](https://finance.yahoo.com/), applies a configurable entry/exit/stoploss strategy,
simulates a virtual trading account (paper-trading backtest), and runs a Monte Carlo simulation over the 
obtained R-multiple distribution (empirical resampling with replacement).

The GetQuotes toolkit was inspired by the various books on trading systems
development written by Dr. Van K. Tharp (<https://vantharpinstitute.com/>).

## 1. What it does (processing steps)

Running `getquotes.py` performs the following processing pipeline for every ticker in the
configured quotes file:

1. **Download data** — fetch OHLC price history from Yahoo Finance and store it as
   `<outdir>/data/<TICKER>_ohlc_raw.csv`.
3. **Add technical indicators** — compute a set of TA indicators (e.g. RSI, ATR, SMA/EMA
   moving averages, Bollinger Bands) over the data.
4. **Generate ENTER/EXIT signals** — apply the configured entry strategy
   (`3EMA`, `SMA` or `BBRSI`), exit strategy (`CE`, `CEE`, `RSI`, `XR`,
   `3EMA`, `SMA` or `BBRSI`) and stoploss method (`3atr` or `percent`) to
   produce entry or exit trading signals.
5. **Plot ticker charts** — save a price/indicator chart per ticker
   (`<outdir>/plots/`), optionally with a separate technical-analysis panel
   (`<outdir>/plots/TA/`).
6. **Build the trades table** — collect every completed and open trade into a combined
   trades table and trades list. From this step the R-multiple distribution resulting from
   the trading system is obtained.
8. **Compute the trading system statistics** — System Quality Number (SQN), win rate,
   Kelly criterion, average R per win/loss, trades/year, etc.
9. **Run the balance simulation** — starting from an initial trading account balance, run a
    paper-trade (backtest), using the enter/exit signals from the configured position sizing strategy
   (`core_equity_risk`, `fixed_dollar_risk`, `fixed_ratio`, `fixed_amount` or `kelly`) and track
   the balance and total value of the trading account over time.
11. **Run a Monte Carlo simulation** — resample from the R-multiple distribution obtained
   from the trades to estimate the range of possible outcomes (empirical resampling with replacement),
   drawdown and loss streaks, and optionally compare against a configurable buy-and-hold benchmark
   (default: iShares MSCI World ETF / `URTH`).
13. **Generate reports** — save all plots, tables (CSV/PDF) and a combined
   `<outdir>/system_summary.pdf` report covering configuration, statistics and
   charts.
14. **Notify via Telegram** *(optional)* — publish the daily ENTER/EXIT/stoploss
    signals and the summary PDF to a configured Telegram chat.

## 2. Configuration

All behaviour is controlled via JSON config files in `config/`:

- `config/system_conf.json` — main configuration: data range, indicator
  settings, strategy selection (enter/exit/stoploss), position sizing,
  account balance, risk per trade, Monte Carlo parameters and the
  `ta_custom` panel list used by `gen_ta_custom`.
- `config/telegram_conf.json` — bot token and chat ID, only required when
  `notify` is `true`.
- `quotes/quotes_sp500.lst`, `quotes/quotes_nasdaq.lst`, `quotes/quotes_dow30.lst` — example lists of tickers to process.

### 2.1 Plot indicators

The price chart (`<outdir>/plots/<TICKER>_plot.png`) and the price panel of
the TA chart (`<outdir>/plots/TA/<TICKER>_plot_ta.png`) always show the same
overlays, picked from three tiers:

- **Fixed** — the close price, ENTER/EXIT markers and trade annotations are
  always shown;
- **Strategy** — an indicator set is shown automatically when it
  matches the configured `enter` strategy: EMA20/50/100 for `3EMA`, the
  fast/slow SMA pair for `SMA`, Bollinger Bands for `BBRSI`. For the Chandelier
  Exit level, the levels are shown, based on the `exit` strategy (`CE` or `CEE`).
- **User-selectable** — the `plot_indicators` list in `system_conf.json` adds
  indicators that aren't tied to a strategy, currently `"BB"` (Bollinger
  Bands) and `"SMA225"` (225-day SMA, bull/bear market reference).

## 3. Environment and Tool Setup

1. Install Python dependencies:

   ```sh
   pip install -r requirements.txt
   ```

   Note: `TA-Lib` requires the underlying TA-Lib C library to be installed
   separately before the Python bindings can be built.
2. Adjust `config/system_conf.json` (and `quotes/quotes_sp500.lst`) to
   match your desired tickers, strategy and account settings.
3. (Optional) Fill in `config/telegram_conf.json` and set `"notify": true` to
   receive daily updates on Telegram.
4. Run the pipeline:

   ```sh
   python getquotes.py [--basedir <path>] [--config <file>] [--outdir <path>] [--loglevel <level>]
   ```

   **Options:**

   `--basedir` defaults to the current working directory and is used to
   locate the `config/` and `quotes/` directories.

   `--config` selects the system configuration file. Relative paths are
   resolved against `basedir`; absolute paths are used as-is. Defaults to
   `config/system_conf.json`.

   `--outdir` sets the output directory where all generated data, plots,
   tables and reports are written. Relative paths are resolved against
   `basedir`; absolute paths are used as-is. Defaults to `out`.

   `--loglevel` controls console verbosity [`DEBUG`, `INFO` (default),
   `WARNING`, `ERROR` or `CRITICAL`].

## 4. Data Output

All generated data, plots, tables and reports are written under the output
directory (default `out/`).The following data, plots and images are produced:

- `<outdir>/data/` — raw and processed OHLC data per ticker
- `<outdir>/plots/` — per-ticker price charts
- `<outdir>/plots/TA/` — next to price, includes indicator panels
- `<outdir>/plots/TA-custom/` — generates custom TA plots (`gen_ta_custom=true`)
- `<outdir>/images/` — system-level plots (trades distribution, balance, Monte Carlo)
- `<outdir>/tables/` — trades table and trades list as CSV files
- `<outdir>/system_summary.pdf`, `full_system_summary.pdf` (`report_type=full`), `trades_table.pdf` and `trades_list.pdf` — combined PDF reports

### 4.1. Example plots

#### Price plot (3EMA strategy)

The plot below shows the price-time chart of Google (Alphabet Inc.). For the triple moving average (3EMA) strategy,
the plot is overlayed with 3 colored moving average lines. The resulting ENTER and EXIT trading signals are also shown on
the plot (green and red triangles). Displayed in the bottom part are the current R-average and in-trade statistics.

<img src="docs/examples/GOOG_plot.png" alt="GOOG price chart" width="900">

#### R-multiple distribution

When applied to the downloaded data, the combination of a specific ticker set, time range and trading strategy incl. the parameters, results in 
a set of trading outcomes which can be expressed as a multiple of the initial risk taken (R-multiple) per trade, where the initial risk per unit is called 1R.
This set of trading outcomes can be show as in the figure below, which shows all individual trade results from left to right expressed as R-multiples.
Also shown in the top right corner of the figure is a summary of the system statistics, which are calculated from the trading outcomes. Two notable and labelled system
statistics include the the average R-multiple (R-mean) and the System Quality Number (SQN).

<img src="docs/examples/system_trades_plot.png" alt="System trades distribution" width="900">

#### Trading backtest

<img src="docs/examples/balance_plot.png" alt="Balance simulation" width="900">

*TODO: description*

### 5.4 Monte Carlo simulation

<img src="docs/examples/monte_carlo_plot.png" alt="Monte Carlo simulation" width="900">

*TODO: description*
