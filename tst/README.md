## Monte Carlo simulator (standalone)

`simulator.py` is a tool which is used to explore how a given R-multiple distribution plays out over many simulated trade sequences. To acchieve this it resamples with replacement from a loaded R-multple distribution (which is considered a simple "bag of
marbles").

The R-multiple distribution is read from a .csv file with a single `Rmul` column (e.g. `out/tables/Rmul_trades.csv`, produced by the main pipeline), and passed via `--rmul-dist`.

### Configuration

Configuration is set from the file `tst/config/simulator_conf.json`:

- `risk_percent` — fraction of balance risked per trade.
- `balance` — starting account balance.
- `sim_len_max` — maximum number of trades per simulated run.
- `iterations` — number of simulation runs.
- `plot_frac` — fraction of the simulated runs that are drawn on the plot. 
   Added to keep dense plots readable.
- `outlier` — used to cap the plot's y-axis (median + `outlier` × stdev of
  final balances).

### Commandline parameters

From the repository root:

```sh
python tst/simulator.py --rmul-dist <path> [--basedir <path>] [--outdir <path>] [--loglevel <level>]
```

**Options**

- `--rmul-dist` is the path to a CSV file containing the R-multiple values
  to resample, in a column named `Rmul`.
- `--basedir` defaults to the current working directory. It does **not**
  affect where the configuration file is loaded from.
- `--outdir` sets the output directory. Relative paths are resolved against
  `basedir`; absolute paths are used as-is. Defaults to `out`.
- `--loglevel` accepts `DEBUG`, `INFO` (default), `WARNING`, `ERROR` or
  `CRITICAL`.

### Output

The output diagram is written to `<outdir>/images/monte_carlo_plot_rmul.png`,
showing a `plot_frac` sample of the simulated balance trajectories plus
summary statistics (median, stdev, min/max, loss streaks, max drawdown, SQN)
computed over all runs.
