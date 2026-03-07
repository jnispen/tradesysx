'''' Read a R-multiple distribution and perform Monte Carlo simulations '''

import pandas as pd
import json
import argparse
import config
import sys
import os
import numpy as np
import seaborn as sns
import math
import statistics
import matplotlib.pyplot as plt


def do_monte_carlo_simulation(rmul_list, conf):
    ''' takes the list of R-multiples and randomly samples from the list (bag of marbles simulation)'''

    print(f"+++ Monte Carlo simulation (sampled) ({conf['iterations']} iterations)")

    # extract Rmul values from the trades list
    Rmul_arr = np.array(rmul_list, dtype=float)  
    
    print(f"+++ Trades total          : {len(Rmul_arr)}")
    print(f"+++ Real Rmul average     : {np.mean(Rmul_arr):.2f}")
    print(f"+++ Real Rmul maximum     : {Rmul_arr.max():.2f}")
    print(f"+++ Real Rmul minimum     : {Rmul_arr.min():.2f}")
    print(f"+++ System Quality Number : {config.sqn:.2f}")

    # sample from the real distribution as measured by the closed trades
    multiset = Rmul_arr.tolist()
    sample_count = 10000
    Rmul_sample = np.random.choice(multiset, size=sample_count, replace=True)

    print(f"+++ Sampled Rmul average  : {np.mean(Rmul_sample):.2f} (10000 samples)")

    # set fixed variables for simulation
    risk = float(conf['risk_percent'])
    print(f"+++ Risk per trade ($)    : {risk*conf['balance']:.2f}")
    print(f"+++ Risk per trade (%)    : {risk*100:.2f}")
    
    sim_runs = conf['iterations']
    # dataframe to hold balance values of all iterations (for visualisation)
    N = sim_runs                                                                       # number of simulations (columns)    
    M = len(Rmul_arr) if len(Rmul_arr) <= conf['sim_len_max'] else conf['sim_len_max'] # number of trades (rows)

    mc_result_df = pd.DataFrame(
        data = [[float('nan')] * N for _ in range(M)],
        columns = [f'{i}' for i in range(N)]
    )

    min_balance = max_balance = float(conf['balance'])
    max_neg_run = 0
    avg_neg_run = 0.0

    # Monte Carlo balance simulation
    for it in range(0, N):

        # reset balance
        balance = float(conf['balance'])

        # draw samples from the original distribution
        Rmul_sampled = np.random.choice(multiset, size=M, replace=True)

        # store longest neg streak
        neg_run = longest_negative_streak(Rmul_sampled)
        avg_neg_run = ((avg_neg_run * it) + neg_run) / (it+1)
        if neg_run > max_neg_run:
            max_neg_run = neg_run 

        for Rs in range(0, len(Rmul_sampled)):
            risk_cur = balance * risk
            trade_result = risk_cur * Rmul_sampled[Rs]
            balance += trade_result

            if balance < min_balance:
                min_balance = balance
            if balance > max_balance:
                max_balance = balance
            
            # store the balance of trade Rs = (row) at it = idx (column)
            mc_result_df.iat[Rs, it] = balance

    # insert first row with the starting balance (same for all simulation runs)
    start_row = [conf['balance']] * N
    start_row_df = pd.DataFrame([start_row], columns=mc_result_df.columns)
    mc_result_df = pd.concat([start_row_df, mc_result_df], ignore_index=True)

    # set global values
    config.max_drawdown = 100.0 - float(min_balance/conf['balance'] * 100)
    config.min_balance = min_balance

    last_row = mc_result_df.iloc[-1]
    print ("+++ MONTE CARLO results")
    print(f"+++ Median                : {last_row.median():,.0f}")
    print(f"+++ Stdev                 : {last_row.std():,.0f}")
    print(f"+++ Max                   : {last_row.max():,.0f}")
    print(f"+++ Min                   : {last_row.min():,.0f}")
    print(f"+++ Loss streak avg       : {avg_neg_run:.0f}")
    print(f"+++ Loss streak max       : {max_neg_run:.0f}")
    print(f"+++ Minimum balance       : {config.min_balance:,.0f}")
    print(f"+++ Max drawdown (%)      : {config.max_drawdown:.1f}")

     # save the balances and plot the result (see simulation plot)
    plot_monte_carlo_results_sampled(mc_result_df, conf, risk, np.mean(Rmul_arr), np.mean(Rmul_sampled), avg_neg_run, max_neg_run)

def longest_negative_streak(values):
    max_len = cur_len = 0
    for v in values:
        if v < 0:
            cur_len += 1
            if cur_len > max_len:
                max_len = cur_len
        else:
            cur_len = 0
    return max_len

def plot_monte_carlo_results_sampled(mc_result_df, conf, risk, Rmul_avg, Rmul_avg_sampled, avg_neg_run, max_neg_run):
    ''' plot the results of the monte carlo simulation '''

    # plot all series of balances for all iterations
    sns.set_style("white")
    ax = mc_result_df.plot(
        figsize=(10, 5),
        color='gray',
        linewidth=0.1,
        marker=None,
        legend=False
    )
    
    # show a marker for the final balance only
    x_last = mc_result_df.index[-1]
    for _, series in mc_result_df.items():
        y_last = series.iloc[-1]
        ax.scatter(
            x_last, y_last,
            marker='o',
            s=4**2,
            color='brown',
            alpha=0.2
        )

    # Y-axis limit = "outlier-cutoff" * standard deviation of trades distribution
    y_max = mc_result_df.iloc[-1].median() + (conf['outlier'] * mc_result_df.iloc[-1].std())
    plt.ylim(bottom=0, top=y_max)

    # plot min-max values as text box
    sim_str = (
        f"Min         : ${mc_result_df.iloc[-1].min():,.0f}\n"
        f"Max         : ${mc_result_df.iloc[-1].max():,.0f}\n"
        f"Std         : ${mc_result_df.iloc[-1].std():,.0f}\n"
        f"Risk        : ${risk*conf['balance']:,.0f}\n"
        f"Risk        : {risk*100:,.2f}%\n"
        f"Loss avg    : {avg_neg_run:.0f}x\n"
        f"Loss max    : {max_neg_run:.0f}x\n"
        f"Max drawdown: {config.max_drawdown:.1f}%\n"
        f"Min balance : ${config.min_balance:,.0f}\n"
        f"Ravg (sim)  : {Rmul_avg_sampled:.2f}\n"
        f"Ravg (real) : {Rmul_avg:.2f}\n"
        f"SQN         : {config.sqn:.2f}"
    )
    ax.text(
        0.03, 0.95, sim_str,
        transform=plt.gca().transAxes,
        fontsize=8,
        fontfamily='Monospace', 
        verticalalignment='top',
        bbox=dict(
            facecolor='white',
            alpha=0.7,
            boxstyle='round,pad=0.5',
            edgecolor='black'
        )
    )

    ax.set_title(f"Monte Carlo simulation [{conf['iterations']}x] (${conf['balance']:,.0f})", fontsize=16, pad=25)
    ax.axhline(conf['balance'], color='green', linestyle='--', label='Balance', linewidth=1, alpha=.7)
    ax.axhline(mc_result_df.iloc[-1].median(), color='brown', linestyle='dotted', linewidth=1.5, alpha=.7)
    
    # from the startbalance and the Rmul average draw a straight line (y = ax + b)
    risk_per_trade = risk * conf['balance']
    a = float(risk_per_trade * Rmul_avg)
    b = float(conf['balance'])
    x_vals = np.array(mc_result_df.index)
    y_vals = a * x_vals + b
    ax.plot(x_vals, y_vals, color='blue', linewidth=2.0, linestyle='--')

    # add label for the last average value
    y_last = a * x_last + b
    plt.text(x_last + 0.5, y_last, f"${y_last:,.0f}", 
        fontsize=10,
        fontfamily='Monospace'
    )

    y_max = plt.ylim()[1]
    y_val = mc_result_df.iloc[-1].median() + 0.035 * y_max
    plt.text(
        -1.5, y_val, f"${mc_result_df.iloc[-1].median():,.0f}",
        fontsize=10,
        fontfamily='Monospace',
        verticalalignment='top'
    )

    ax.set_xlabel('Trade')
    ax.set_ylabel('Balance (USD)')
    ax.grid(True, which='both', linestyle='dotted', alpha=0.5)

    plt.savefig(data_path("out/reports", "monte_carlo_plot.png"), dpi=150)
    plt.close()

def data_path(*parts):
    """Return a string path inside the root output directory."""
    p = os.path.join(config.basedir, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p

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
    config.basedir = base_dir
    print("+++ base directory: " + str(config.basedir))

    # load system confguration
    conf_file = data_path(str(config.basedir), 'config/simulator_conf.json')
    try:
        with open(conf_file) as f:
            print(f"+++ configuration file: {conf_file}")
            conf = json.loads(f.read())
    except Exception as e:
        print(f"+++ failed to load configuration file: {e}")
        sys.exit(1)
    
    rmul_list = [
            20, 20,                         # 2 × 20
            10, 10, 10,                     # 3 × 10
            2, 2, 2, 2, 2, 2, 2, 2, 2, 2,
            2, 2, 2, 2, 2, 2, 2, 2, 2, 2,   # 20 × 2
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1,   # 30 × 1
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, # 40 × ‑1
            -5, -5, -5, -5, -5              # 5 × ‑5
    ]

    Ravg = statistics.mean(rmul_list)
    Rstd = statistics.stdev(rmul_list)
    config.sqn = (Ravg / Rstd) * math.sqrt(len(rmul_list)) if len(rmul_list) < 100 else (Ravg / Rstd) * math.sqrt(100)
    
    do_monte_carlo_simulation(rmul_list, conf)

if __name__ == "__main__":
    main()
