## System Settings Reference (`system_conf.json`)

The list below details every setting in `config/system_conf.json`. Each entry gives a short
explanation; where a setting only accepts a fixed set of values (or a type), those are listed
in brackets after the setting name. Everything else takes a free value (a number, string,
date, or path).

A leading underscore (e.g. `_end`) is a "comment-out" convention — the code reads the key *without* the underscore, so an underscored key is ignored until you rename it. 

A note on **position sizing** and **strategy** settings: many knobs are only live for a particular strategy selection (called out per entry); editing a knob whose strategy isn't selected has no effect.

---

**quotefile** — [`path`]\
Path (relative to the base dir) to the JSON quote list of `{ticker: description}` pairs to run the system over, e.g. `quotes/quotes_sp500.lst`.

**loglevel** — [`debug`/`info`/`warning`/`error`/`critical`]\
Console logging verbosity. Sets the same level as the `--loglevel` commandline flag. Precedence: an explicit `--loglevel` on the commandline wins; otherwise this config value is used; defaults to `info`.

**follow_only** — [`true`/`false`]\
When `true`, only downloads and charts the configured tickers — no signals, stats, simulation, or report are produced. Used to follow and eyeball price charts.

**benchmark** — [`true`/`false`]\
Show a buy-and-hold benchmark (HODL) to compare the trading system against.

**bm_ticker** — [`string`]\
Benchmark instrument. Either **any ticker symbol** (buy-and-hold over the run period, e.g. `URTH`), or the special value `quote-lst` — an equal-weight buy-and-hold basket of *every* ticker in `quotefile`.

**bm_desc** — [`string`]\
Free-text description of the benchmark, shown in the report (e.g. `iShares MSCI World ETF`).

**notify** — [`true`/`false`]\
Send a Telegram notification when the run finishes (reads `config/telegram_conf.json`). Ignored in `follow_only` mode.

**update_data** — [`true`/`false`]\
Download fresh OHLC data from yfinance. When `false`, reuses the cached CSVs in `out/data/`.

**process_data** — [`true`/`false`]\
Add technical indicators and generate ENTER/EXIT signals. When `false`, reuses previously processed data.

**gen_plots** — [`true`/`false`]\
Generate the per-ticker price plots.

**gen_ta_plots** — [`true`/`false`]\
Generate the per-ticker technical-analysis (TA) plots (indicator panels).

**plot_indicators** — [`BB`/`SMA225`]\
List of overlays drawn on the price panel. `BB` = Bollinger Bands, `SMA225` = 225-period SMA. Example: `["SMA225"]`.

**gen_ta_custom** — [`true`/`false`]\
Generate the ad-hoc custom TA panels defined by `ta_custom`. Must be `false` if `ta_custom` is empty.

**ta_custom** — [`RSI`/`ADX`/`FI`/`OBV`/`MACD`/`DI`/`ATR`/`CCI`/`ROC`/`MFI`]\
List of extra indicator panels to plot, one panel each. Only used when `gen_ta_custom` is `true`.

**report_type** — [`short`/`full`]\
Selects the summary report variant; both write `out/system_summary.pdf` (`full` additionally appends every ticker's plot).

**report_style** — [`classic`/`styled`]\
Selects the look of `out/system_summary.pdf`. `classic` is the original report; `styled` produces a professionally formatted report with KPI cards, a strategy-vs-benchmark comparison, restyled charts and a benchmark table. Defaults to `styled` when absent.

**stloss** — [`3atr`/`percent`]\
Stop-loss strategy. `3atr` = 3×ATR below the close, `percent` = stoploss set as a percentage below the entry price (see `stoploss`).

**enter** — [`3EMA`/`SMA`/`BBRSI`/`MACD`]\
Entry strategy.

**exit** — [`CE`/`CEE`/`RSI`/`XR`/`3EMA`/`SMA`/`MACD`/`BBRSI`]\
Exit strategy.

**start** — [`date`]\
History start date, `YYYY-MM-DD`. Data is downloaded from this date to today.

**_end** — [`date`] (default: **Disabled (leading underscore)**)\
Rename to `end` to set an explicit end date (`YYYY-MM-DD`) instead of downloading up to today.

**_period** — [`string`] (default: **Disabled (leading underscore)**)\
Rename to `period` to download by rolling look-back (e.g. `5y`) *instead of* using `start`. Specify either `start` or `period`, not both.

**_interval** — [`string`] (default: **Disabled (leading underscore)**)\
Rename to `interval` to set the bar interval (e.g. `1d`, `1wk`). Defaults to `1d` when absent.

**date_int** — [`integer`]\
Spacing, in days, between date ticks on the plot x-axes.

**stoploss** — [`float`]\
Multiplier of the close used as the stop when `stloss` is `percent` (e.g. `0.92` = stop 8% below the close). Ignored when `stloss` is `3atr`.

**intrade_wait** — [`integer`]\
Minimum number of bars a position must be held before the `CE`, `CEE`, and `XR` exits are allowed to trigger.

**trading_fee** — [`float`]\
Transaction fee as a percentage of the gross trade value, charged on both entry and exit (e.g. `0.2` = 0.2%).

**min_invest** — [`float`]\
Minimum capital per trade; if the sized position would invest less than this, the trade is skipped.

**balance** — [`float`]\
Starting account balance for the paper-trading simulation.

**pos_sizing** — [`core_equity_risk`/`fixed_dollar_risk`/`fixed_ratio`/`fixed_amount`/`kelly`]\
Position-sizing method. `core_equity_risk` = risk `risk_percent` of equity, `fixed_dollar_risk` = risk `risk_amount`, `fixed_ratio` = invest `balance / pos_ratio`, `fixed_amount` = invest `pos_amount`, `kelly` = Kelly-fraction of equity.

**risk_percent** — [`float`]\
Fraction of equity risked per trade (e.g. `0.01` = 1%). Only used when `pos_sizing` is `core_equity_risk`.

**risk_amount** — [`float`]\
Fixed dollar risk per trade. Only used when `pos_sizing` is `fixed_dollar_risk`.

**pos_ratio** — [`number`]\
Divisor of the balance used as the position size. Only used when `pos_sizing` is `fixed_ratio`.

**pos_amount** — [`number`]\
Fixed capital invested per position. Only used when `pos_sizing` is `fixed_amount`.

**kelly_ratio** — [`float`]\
Fraction of the full Kelly criterion to apply (e.g. `0.5` = half Kelly). Only used when `pos_sizing` is `kelly`.

**R_profit** — [`number`]\
R-multiple profit target that triggers an exit. Only used by the `XR` exit strategy.

**adx_trend** — [`number`]\
ADX threshold used as the trend-strength filter in the `3EMA`, `SMA`, and `MACD` enter/exit signals.

**rsi_low** — [`float`]\
RSI oversold threshold used by the `BBRSI` entry.

**rsi_high** — [`float`]\
RSI overbought threshold used by the `RSI` and `BBRSI` exits.

**rsi_time** — [`integer`]\
Period (bars) for the RSI indicator.

**atr_time** — [`integer`]\
Period (bars) for the ATR indicator (also drives the `3atr` stop and Chandelier Exit).

**sma_fast** — [`integer`]\
Period of the fast SMA (used by the `SMA` strategy).

**sma_slow** — [`integer`]\
Period of the slow SMA (used by the `SMA` strategy).

**macd_fast** — [`integer`]\
Fast EMA period for MACD (used by the `MACD` strategy).

**macd_slow** — [`integer`]\
Slow EMA period for MACD.

**macd_signal** — [`integer`]\
Signal-line period for MACD.

**montecarlo** — [`true`/`false`]\
Run the Monte Carlo simulation step on the resulting trades.

**sim_len_max** — [`integer`]\
Maximum number of trades per simulated equity sequence.

**iterations** — [`integer`]\
Number of Monte Carlo iterations (simulated trade sequences).

**plot_frac** — [`float`]\
Fraction of the simulated equity curves actually drawn on the Monte Carlo plot (e.g. `0.05` = 5%). All iterations still count toward the statistics.

**outlier** — [`number`]\
Y-axis cutoff for the Monte Carlo plot, set to `median + outlier × std` of the final-balance distribution.
