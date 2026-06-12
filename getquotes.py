'''' Get quotes from Yahoo Finance and plot potential trades '''

import pandas as pd
import json
import asyncio
import argparse
import sys
import os

from datetime import datetime

import utils as ut
from tables import TotalTradesList, TradesTable
from context import RunContext, SystemStats

last_close_date = None

def update_quotes(conf, ctx):

    ohlc_filename = 'ohlc_raw.csv'
    outp_filename = 'data_out.csv'
    total_trades_table = TradesTable()
    total_trades_list = TotalTradesList()
    stats = SystemStats()
    telegram_df = pd.DataFrame(columns=['Ticker', 'Close', 'Signal','STLoss'])

    config_str = '++- start: ' + str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print(config_str)

    config_str = '+++ configuration:\n' + json.dumps(conf, indent=2)
    print(config_str)
    conf_str = json.dumps(conf, indent=2)

    quote_file = ctx.path(conf["quotefile"])
    with open(quote_file) as f:
        quotes = json.loads(f.read())

    # add benchmark to dict
    quotes["URTH"] = "MSCI World (US4642863926)"
    quotes_str = json.dumps(quotes, indent=2)

    # 1. read quotes from yfinance and save raw OHLC file
    if conf['update_data'] == True:
        ut.get_quotes_data(quotes, conf, ohlc_filename, ctx)

    if conf['process_data'] == True:
        num_quotes = len(quotes)
        config_str = '+++ processing quotes (' + str(num_quotes) + ')'
        print(config_str)

        trades_table_frames = []
        trades_list_frames = []
        telegram_frames = []

        idx = 1
        for ticker, desc in quotes.items():
            print(f'{idx} - {ticker}: {desc}\n', end='')
            idx += 1

            # 2. read data from disk
            dff = pd.read_csv(ctx.path('out/data',f"{ticker}_{ohlc_filename}"))
            dff.set_index('Date', inplace=True)

            # 3. add TA indicators
            dft = ut.add_technical_indicators(dff, conf)

            # 4. add ENTER and EXIT signals
            dft = ut.add_trading_signals(dft, conf)
            last_close_date = pd.to_datetime(dft.index[-1])
            first_close_date = pd.to_datetime(dft.index[0])

            # 5. generate plots and save figures
            if conf['gen_plots'] == True:
                ut.ticker_plot(dft, ticker, desc, conf, ctx)
            if conf['gen_ta_plots'] == True:
                ut.ticker_plot_ta(dft, ticker, desc, conf, ctx)

            # 6. generate the table and list of trades (timesequence for simulation)
            trade_table, trade_list = ut.generate_trading_table(dft, ticker)
            trades_table_frames.append(trade_table.df)
            trades_list_frames.append(trade_list.df)

            # add ticker and signals to daily msg
            cols = ['Close', 'Signal','STLoss']
            last_rec = dft[cols].tail(1).copy()
            last_rec['Ticker'] = ticker
            telegram_frames.append(last_rec)

            # 7. save processed data to .csv
            dft.to_csv(ctx.path('out/data',f"{ticker}_{outp_filename}"))

        # combine the per-ticker frames collected above into the totals
        if trades_table_frames:
            total_trades_table.df = pd.concat([total_trades_table.df] + trades_table_frames)
        if trades_list_frames:
            total_trades_list.df = pd.concat([total_trades_list.df] + trades_list_frames)
        if telegram_frames:
            telegram_df = pd.concat([telegram_df] + telegram_frames, ignore_index=True)
            telegram_df[['Close', 'STLoss']] = telegram_df[['Close', 'STLoss']].round(2)

    # 8. save combined trades data to .csv
    ut.save_trades_table(total_trades_table.df, conf, ctx)

    # 9. generate some system statistics
    if conf['process_data'] == True:
        trading_period = (last_close_date - first_close_date).days
        system_stat = ut.generate_system_stats(total_trades_table.df, trading_period, ctx, stats)
        system_stats = system_stat.to_string(index=False)
        print ("======= system statistics =========")
        print (system_stats)
        print ("===================================")

    # 10. virtual trading balance simulation
    balance_df = ut.do_balance_simulation(total_trades_list.df, total_trades_table.df, conf, last_close_date, ctx, stats)
    ut.balance_plot(balance_df, conf, ctx)

    # 12. monte carlo smulation to test position sizing strategy
    if conf['montecarlo'] == True:
        # run monte carlo simulation by shuffling the existing trades
        #ut.do_monte_carlo_simulation_shuffled(total_trades_table.df, conf, ctx, stats, last_close_date)

        # run monte carlo simulation by sampling from the fitted distribution
        ut.do_monte_carlo_simulation_sampled(total_trades_table.df, conf, ctx, stats)

    # 11. generate a complete system summary report in a single pdf
    ut.generate_summary_report(system_stat, conf_str, quotes_str, ctx)

    print('+++ processing finished')

    if conf['notify'] == True:
        # 12. send status updates to the Telegram bot
        telegram_df = telegram_df.sort_values(by='Ticker', ascending=True)
        telegram_df = telegram_df.reset_index(drop=True)
        telegram_df.index = telegram_df.index + 1
        last_col = telegram_df.columns[-1]
        telegram_df[last_col] = telegram_df[last_col].apply(lambda x: f'({x})')
        telegram_df = telegram_df[['Ticker', 'Close', 'STLoss', 'Signal']]
        msg_text = telegram_df.to_string(index=True, justify='left', header=False)
        print(msg_text)

        asyncio.run(ut.bot_signal_update(ctx, last_close_date, msg_text))
        response = ut.bot_summary_update(ctx, ctx.path("out", "system_summary.pdf"))
        if response.ok:
            print('+++ telegram updates sent')
        else:
            print('+++ error sending update: ', response.text)
        
    config_str = '++- stop: ' + str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print(config_str + '\n')

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
    conf_file = ctx.path('config/system_conf.json')
    try:
        with open(conf_file) as f:
            print(f"+++ configuration file: {conf_file}")
            conf = json.loads(f.read())
    except Exception as e:
        print(f"+++ failed to load configuration file: {e}")
        sys.exit(1)

    # load telegram chat id and bot token if configured
    if conf['notify'] == True:
        ta_file = ctx.path('config/telegram_conf.json')
        with open(ta_file) as f:
            print(f"+++ telegram configuration file: {ta_file}")
            ta_conf = json.loads(f.read())
        ctx.bot_token = ta_conf['bot_token']
        ctx.chat_id = ta_conf['chat_id']

    update_quotes(conf, ctx)

if __name__ == "__main__":
    main()
