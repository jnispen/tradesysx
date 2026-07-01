# Monte Carlo simulator (standalone)

`simulator.py` is a tool used to explore how a given R-multiple
distribution plays out over many simulated trade sequences ("bag of
marbles" resampling with replacement).

The R-multiple distribution is read from a CSV file with an `Rmul` column
(e.g. `out/tables/Rmul_trades.csv`, produced by the main pipeline), passed
via `--rmul-dist`.

## Running it

From the repository root:

```sh
python tst/simulator.py --rmul-dist <path> [--basedir <path>] [--outdir <path>] [--loglevel <level>]
```

- `--rmul-dist` is the path to a CSV file containing the R-multiple values
  to resample, in a column named `Rmul`.
- `--basedir` defaults to the current working directory. It does **not**
  affect where the configuration file is loaded from.
- `--outdir` sets the output directory. Relative paths are resolved against
  `basedir`; absolute paths are used as-is. Defaults to `out`.
- `--loglevel` accepts `DEBUG`, `INFO` (default), `WARNING`, `ERROR` or
  `CRITICAL`.

## Configuration

`tst/config/simulator_conf.json` (always loaded relative to this script,
regardless of `--basedir`):

- `risk_percent` — fraction of balance risked per trade.
- `balance` — starting account balance.
- `sim_len_max` — maximum number of trades per simulated run.
- `iterations` — number of simulation runs.
- `outlier` — used to cap the plot's y-axis (median + `outlier` × stdev of
  final balances).

## Output

The plotted output is written to `<outdir>/images/monte_carlo_plot.png`,
showing all simulated balance trajectories plus summary statistics (median,
stdev, min/max, loss streaks, max drawdown, SQN).
