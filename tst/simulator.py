'''' Read a R-multiple distribution and perform Monte Carlo simulations '''

import json
import argparse
import logging
import sys
import os
import numpy as np
import pandas as pd
import math
import statistics

# make the repo root's parent directory importable as the `getquotes` package
# when running as `python tst/simulator.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from getquotes.context import RunContext, SystemStats
from getquotes.logging_setup import setup_logging, add_logging_arguments
from getquotes.utils import run_monte_carlo_sampled

logger = logging.getLogger(__name__)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--basedir',
        type=str,
        default='',
        help='Base directory'
    )
    parser.add_argument(
        '--outdir',
        type=str,
        default='out',
        help='Output directory (relative to basedir or absolute)'
    )
    parser.add_argument(
        '--rmul-dist',
        type=str,
        required=True,
        help='CSV file containing R-multiple distribution values in a single column (Rmul)'
    )
    add_logging_arguments(parser)
    args = parser.parse_args()
    setup_logging(args.loglevel)

    # set base directory
    if args.basedir:
        base_dir = os.path.abspath(args.basedir)
    else:
        base_dir = os.getcwd()
    outdir = os.path.abspath(os.path.join(base_dir, args.outdir)) if not os.path.isabs(args.outdir) else args.outdir
    ctx = RunContext(basedir=base_dir, outdir=outdir)
    logger.info("Base directory         : " + str(ctx.basedir))
    logger.info("Output directory       : " + str(ctx.outdir))

    # load system confguration (relative to this script, not --basedir)
    conf_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'simulator_conf.json')
    try:
        with open(conf_file) as f:
            logger.info(f"Configuration file     : {conf_file}")
            conf = json.loads(f.read())
    except Exception as e:
        logger.critical(f"failed to load configuration file: {e}")
        sys.exit(1)

    rmul_dist = os.path.abspath(args.rmul_dist)
    try:
        rmul_df = pd.read_csv(rmul_dist)
        rmul_list = rmul_df['Rmul'].dropna().tolist()
        logger.info(f"R-multiple file        : {rmul_dist}")
    except Exception as e:
        logger.critical(f"failed to load R-multiple file: {e}")
        sys.exit(1)

    Ravg = statistics.mean(rmul_list)
    Rstd = statistics.stdev(rmul_list)
    sqn = (Ravg / Rstd) * math.sqrt(len(rmul_list)) if len(rmul_list) < 100 else (Ravg / Rstd) * math.sqrt(100)
    stats = SystemStats(sqn=sqn)

    Rmul_arr = np.array(rmul_list, dtype=float)
    risk = float(conf['risk_percent'])

    logger.info("==== Monte Carlo simulation ====")
    output_filename = "monte_carlo_plot_rmul.png"
    run_monte_carlo_sampled(Rmul_arr, conf, ctx, stats, risk,
                            output_filename=output_filename, benchmark=None)
    logger.info("================================")
    logger.info(f"Simulation plot saved  : {ctx.outpath('images', output_filename)}")

if __name__ == "__main__":
    main()
