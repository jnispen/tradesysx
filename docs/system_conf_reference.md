# `system_conf.json` settings reference

Every setting in `config/system_conf.json`, in file order. Each entry gives a short
explanation; where a setting only accepts a fixed set of values, those values are listed.
Everything else takes a free value (a number, string, date, or path).

A note on **disabled keys**: a leading underscore (e.g. `_end`) is a "comment-out"
convention — the code reads the key *without* the underscore, so an underscored key is
ignored until you rename it. A note on **position sizing** and **strategy** settings: many
knobs are only live for a particular strategy selection (called out per entry); editing a
knob whose strategy isn't selected has no effect.

---

### `quotefile`
Path (relative to the base dir) to the JSON quote list of `{ticker: description}` pairs to
run the system over, e.g. `quotes/quotes_sp500.lst`.

### `follow_only`
`true` / `false`. When `true`, only downloads and charts the configured tickers — no
signals, stats, simulation, or report are produced. Use it to eyeball price charts.

### `benchmark`
`true` / `false`. Whether to compute and show a buy-and-hold benchmark to compare the
system against.

### `bm_ticker`
Benchmark instrument. Either **any ticker symbol** (bought-and-held over the run period,
e.g. `URTH`), or the special value `quote-lst` — an equal-weight buy-and-hold basket of
*every* ticker in `quotefile`.

### `bm_desc`
Free-text description of the benchmark, shown in the report (e.g. `iShares MSCI World ETF`).

### `notify`
`true` / `false`. Send a Telegram notification when the run finishes (reads
`config/telegram_conf.json`). Ignored in `follow_only` mode.

### `update_data`
`true` / `false`. Download fresh OHLC data from yfinance. When `false`, reuses the cached
CSVs in `out/data/`.

### `process_data`
`true` / `false`. Add technical indicators and generate ENTER/EXIT signals. When `false`,
reuses previously processed data.

### `gen_plots`
`true` / `false`. Generate the per-ticker price plots.

### `gen_ta_plots`
`true` / `false`. Generate the per-ticker technical-analysis plots (indicator panels).

### `plot_indicators`
List of overlays drawn on the price panel. Fixed set: `BB` (Bollinger Bands), `SMA225`.
Example: `["SMA225"]`.

### `gen_ta_custom`
`true` / `false`. Generate the ad-hoc custom TA panels defined by `ta_custom`. Must be
`false` if `ta_custom` is empty.

### `ta_custom`
List of extra indicator panels to plot, one panel each. Fixed set: `RSI`, `ADX`, `FI`,
`OBV`, `MACD`, `DI`, `ATR`, `CCI`, `ROC`, `MFI`. Only used when `gen_ta_custom` is `true`.

### `report_type`
Fixed set: `short`, `full`. Selects the summary report variant
(`out/system_summary.pdf` vs `out/system_summary_full.pdf`).

### `stloss`
Stop-loss strategy. Fixed set: `3atr` (3×ATR below the close), `percent` (a percentage of
the close — see `stoploss`).

### `enter`
Entry strategy. Fixed set: `3EMA`, `SMA`, `BBRSI`, `MACD`.

### `exit`
Exit strategy. Fixed set: `CE`, `CEE`, `RSI`, `XR`, `3EMA`, `SMA`, `MACD`, `BBRSI`.

### `start`
History start date, `YYYY-MM-DD`. Data is downloaded from this date to today.

### `_end`
**Disabled** (leading underscore). Rename to `end` to set an explicit end date
(`YYYY-MM-DD`) instead of downloading up to today.

### `_period`
**Disabled** (leading underscore). Rename to `period` to download by rolling look-back
(e.g. `5y`) *instead of* using `start`. Specify either `start` or `period`, not both.

### `_interval`
**Disabled** (leading underscore). Rename to `interval` to set the bar interval
(e.g. `1d`, `1wk`). Defaults to `1d` when absent.

### `date_int`
Integer. Spacing, in days, between date ticks on the plot x-axes.

### `stoploss`
Float multiplier of the close used as the stop when `stloss` is `percent`
(e.g. `0.92` = stop 8% below the close). Ignored when `stloss` is `3atr`.

### `intrade_wait`
Integer. Minimum number of bars a position must be held before the `CE`, `CEE`, and `XR`
exits are allowed to trigger.

### `trading_fee`
Float. Transaction fee as a percentage of the gross trade value, charged on both entry and
exit (e.g. `0.2` = 0.2%).

### `min_invest`
Float. Minimum capital per trade; if the sized position would invest less than this, the
trade is skipped.

### `risk_percent`
Float fraction of equity risked per trade (e.g. `0.01` = 1%). Only used when `pos_sizing`
is `core_equity_risk`.

### `risk_amount`
Float. Fixed dollar risk per trade. Only used when `pos_sizing` is `fixed_dollar_risk`.

### `balance`
Float. Starting account balance for the paper-trading simulation.

### `pos_sizing`
Position-sizing method. Fixed set: `core_equity_risk` (risk `risk_percent` of equity),
`fixed_dollar_risk` (risk `risk_amount`), `fixed_ratio` (invest `balance / pos_ratio`),
`fixed_amount` (invest `pos_amount`), `kelly` (Kelly-fraction of equity).

### `pos_ratio`
Number. Divisor of the balance used as the position size. Only used when `pos_sizing` is
`fixed_ratio`.

### `pos_amount`
Number. Fixed capital invested per position. Only used when `pos_sizing` is `fixed_amount`.

### `kelly_ratio`
Float. Fraction of the full Kelly criterion to apply (e.g. `0.5` = half Kelly). Only used
when `pos_sizing` is `kelly`.

### `R_profit`
Number. R-multiple profit target that triggers an exit. Only used by the `XR` exit
strategy.

### `adx_trend`
Number. ADX threshold used as the trend-strength filter in the `3EMA`, `SMA`, and `MACD`
enter/exit signals.

### `rsi_low`
Float. RSI oversold threshold used by the `BBRSI` entry.

### `rsi_high`
Float. RSI overbought threshold used by the `RSI` and `BBRSI` exits.

### `rsi_time`
Integer. Period (bars) for the RSI indicator.

### `atr_time`
Integer. Period (bars) for the ATR indicator (also drives the `3atr` stop and Chandelier
Exit).

### `sma_fast`
Integer. Period of the fast SMA (used by the `SMA` strategy).

### `sma_slow`
Integer. Period of the slow SMA (used by the `SMA` strategy).

### `macd_fast`
Integer. Fast EMA period for MACD (used by the `MACD` strategy).

### `macd_slow`
Integer. Slow EMA period for MACD.

### `macd_signal`
Integer. Signal-line period for MACD.

### `montecarlo`
`true` / `false`. Run the Monte Carlo simulation step on the resulting trades.

### `sim_len_max`
Integer. Maximum number of trades drawn per simulated equity sequence.

### `iterations`
Integer. Number of Monte Carlo iterations (simulated sequences).

### `plot_frac`
Float fraction of the simulated equity curves actually drawn on the Monte Carlo plot
(e.g. `0.05` = 5%). All iterations still count toward the statistics.

### `outlier`
Number. Y-axis cutoff for the Monte Carlo plot, set to `median + outlier × std` of the
final-balance distribution.
