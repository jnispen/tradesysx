'''' Read a R-multiple distribution and perform Monte Carlo simulations '''

import json
import argparse
import sys
import os
import math
import statistics
import numpy as np

import utils as ut
from context import RunContext, SystemStats


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--basedir',
        type=str,
        default='',
        help='Base directory'
    )
    args = parser.parse_args()

    # set base directory
    if args.basedir:
        base_dir = os.path.abspath(args.basedir)
    else:
        base_dir = os.getcwd()
    ctx = RunContext(basedir=base_dir)
    print("+++ base directory: " + str(ctx.basedir))

    # load system confguration
    conf_file = ctx.path('config/simulator_conf.json')
    try:
        with open(conf_file) as f:
            print(f"+++ configuration file: {conf_file}")
            conf = json.loads(f.read())
    except Exception as e:
        print(f"+++ failed to load configuration file: {e}")
        sys.exit(1)

    rmul_list = [
            20, 20,                         # 2 × 20
            10, 10, 10,                     # 3 × 10
            2, 2, 2, 2, 2, 2, 2, 2, 2, 2,
            2, 2, 2, 2, 2, 2, 2, 2, 2, 2,   # 20 × 2
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1,   # 30 × 1
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, # 40 × ‑1
            -5, -5, -5, -5, -5              # 5 × ‑5
    ]

    Ravg = statistics.mean(rmul_list)
    Rstd = statistics.stdev(rmul_list)
    sqn = (Ravg / Rstd) * math.sqrt(len(rmul_list)) if len(rmul_list) < 100 else (Ravg / Rstd) * math.sqrt(100)

    # this distribution isn't tied to actual trades, so derive stats directly
    stats = SystemStats(sqn=sqn, trades_num=len(rmul_list), trades_len=365)
    risk = float(conf['risk_percent'])

    ut.run_monte_carlo_sampled(np.array(rmul_list, dtype=float), conf, ctx, stats, risk)

if __name__ == "__main__":
    main()
