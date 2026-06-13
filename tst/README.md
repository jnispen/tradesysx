### Standalone Monte Carlo simulator

`simulator.py` is a small tool used to explore how a given R-multiple
distribution plays out over many simulated trade sequences ("bag of
marbles" resampling). It reuses the logging setup (`logging_setup.py`) and
the sampled Monte Carlo simulation/plotting code (`run_monte_carlo_sampled`
in `utils.py`) from the main `getquotes.py` pipeline, so it has the same
dependencies (TA-Lib, yfinance, WeasyPrint, etc.) even though it doesn't use
most of them. Its own R-multiple list, configuration file, and SQN
computation remain specific to this tool. Unlike the main pipeline, it does
not download or plot the URTH buy-and-hold benchmark, since that comparison
has no meaning for a synthetic R-multiple distribution.

Currently the R-multiple distribution is a hardcoded list in `main()` —
edit `simulator.py` directly to try different distributions.

#### Running it

From the repository root:

```sh
python tst/simulator.py [--basedir <path>] [--loglevel <level>]
```

- `--basedir` defaults to the current working directory and controls where
  output is written (see below). It does **not** affect where the
  configuration file is loaded from.
- `--loglevel` accepts `DEBUG`, `INFO` (default), `WARNING`, `ERROR` or
  `CRITICAL`.

#### Configuration

`tst/config/simulator_conf.json` (always loaded relative to this script,
regardless of `--basedir`):

- `risk_percent` — fraction of balance risked per trade.
- `balance` — starting account balance.
- `sim_len_max` — maximum number of trades per simulated run.
- `iterations` — number of simulation runs.
- `outlier` — used to cap the plot's y-axis (median + `outlier` × stdev of
  final balances).

#### Output

A single plot is written to `<basedir>/out/reports/monte_carlo_plot.png`,
showing all simulated balance trajectories plus summary statistics (median,
stdev, min/max, loss streaks, max drawdown, SQN).
