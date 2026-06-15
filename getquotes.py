'''' Get quotes from Yahoo Finance and plot potential trades '''

import pandas as pd
import json
import asyncio
import argparse
import logging
import sys
import os

from datetime import datetime

# make the repo root's parent directory importable as the `getquotes` package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from getquotes import utils as ut
from getquotes.tables import TotalTradesList, TradesTable
from getquotes.context import RunContext, SystemStats
from getquotes.logging_setup import setup_logging, add_logging_arguments

logger = logging.getLogger(__name__)

def update_quotes(conf, ctx):

    ohlc_filename = 'ohlc_raw.csv'
    outp_filename = 'data_out.csv'
    total_trades_table = TradesTable()
    total_trades_list = TotalTradesList()
    stats = SystemStats()
    telegram_df = pd.DataFrame(columns=['Ticker', 'Close', 'Signal','STLoss'])
    last_close_date = pd.Timestamp("1900-01-01")

    config_str = '==== System configuration ====\n' + json.dumps(conf, indent=2)
    logger.debug(config_str)
    conf_str = json.dumps(conf, indent=2)

    quote_file = ctx.path(conf["quotefile"])
    with open(quote_file) as f:
        quotes = json.loads(f.read())

    # add benchmark to dict
    quotes["URTH"] = "MSCI World (US4642863926)"
    quotes_str = json.dumps(quotes, indent=2)

    # 1. read quotes from yfinance and save raw OHLC file
    if conf['update_data'] == True:
        logger.info(f'==== [1/8] Downloading quote data ({len(quotes)}) ====')
        ut.get_quotes_data(quotes, conf, ohlc_filename, ctx)
    else:
        logger.info('==== [1/8] Downloading quote data: skipped (update_data=false) ====')

    if conf['process_data'] == True:
        logger.info('==== [2/8] Processing tickers ====')

        trades_table_frames = []
        trades_list_frames = []
        telegram_frames = []

        idx = 1
        for ticker, desc in quotes.items():
            logger.info(f'{idx} - {ticker}: {desc}')
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
    else:
        logger.info('==== [2/8] Processing tickers: skipped (process_data=false) ====')

    # 8. save combined trades data to .csv
    logger.info('==== [3/8] Saving trades table ====')
    ut.save_trades_table(total_trades_table.df, conf, ctx)

    # 9-12. system statistics, balance simulation, monte carlo and report all
    # require the per-ticker data processed in step 2, so skip them together
    if conf['process_data'] == True and total_trades_table.df.empty:
        logger.info('==== No trades found for the current parameter set - stopping ====')
        logger.info('==== [4/8] Generating system statistics: skipped (no trades) ====')
        logger.info('==== [5/8] Running trading balance simulation (backtest): skipped (no trades) ====')
        logger.info('==== [6/8] Running Monte Carlo simulation: skipped (no trades) ====')
        logger.info('==== [7/8] Generating summary report: skipped (no trades) ====')
    elif conf['process_data'] == True:
        # 9. generate some system statistics
        logger.info('==== [4/8] Generating system statistics ====')
        trading_period = (last_close_date - first_close_date).days
        system_stat = ut.generate_system_stats(total_trades_table.df, trading_period, ctx, stats)
        system_stats = system_stat.to_string(index=False)
        logger.info(system_stats)

        # 10. virtual trading balance simulation
        logger.info('==== [5/8] Running trading balance simulation (backtest) ====')
        balance_df = ut.do_balance_simulation(total_trades_list.df, total_trades_table.df, conf, last_close_date, ctx, stats)
        ut.balance_plot(balance_df, conf, ctx)

        # 12. monte carlo smulation to test position sizing strategy
        if conf['montecarlo'] == True:
            logger.info('==== [6/8] Running Monte Carlo simulation ====')
            # run monte carlo simulation by sampling from the trade distribution ('bag of marbles' simulation)
            ut.do_monte_carlo_simulation_sampled(total_trades_table.df, conf, ctx, stats)
        else:
            logger.info('==== [6/8] Running Monte Carlo simulation: skipped (montecarlo=false) ====')

        # 11. generate a complete system summary report in a single pdf
        logger.info('==== [7/8] Generating summary report ====')
        ut.generate_summary_report(system_stat, conf_str, quotes_str, ctx)
    else:
        logger.info('==== [4/8] Generating system statistics: skipped (process_data=false) ====')
        logger.info('==== [5/8] Running trading balance simulation (backtest): skipped (process_data=false) ====')
        logger.info('==== [6/8] Running Monte Carlo simulation: skipped (process_data=false) ====')
        logger.info('==== [7/8] Generating summary report: skipped (process_data=false) ====')

    if conf['notify'] == True and conf['process_data'] == True:
        # 12. send status updates to the Telegram bot
        logger.info('==== [8/8] Sending Telegram notification ====')
        telegram_df = telegram_df.sort_values(by='Ticker', ascending=True)
        telegram_df = telegram_df.reset_index(drop=True)
        telegram_df = telegram_df[['Ticker', 'Close', 'STLoss', 'Signal']]
        logger.debug(telegram_df.to_string(index=False))

        asyncio.run(ut.bot_signal_update(ctx, last_close_date, telegram_df))
        asyncio.run(ut.bot_signal_alert(ctx, last_close_date, telegram_df))
        response = ut.bot_summary_update(ctx, ctx.path("out", "system_summary.pdf"))
        if response.ok:
            logger.info('- response OK, updates sent successfully')
        else:
            logger.error(f'error sending update: {response.text}')
    elif conf['notify'] == True:
        logger.info('==== [8/8] Sending Telegram notification: skipped (process_data=false) ====')
    else:
        logger.info('==== [8/8] Sending Telegram notification: skipped (notify=false) ====')

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--basedir',
        type=str,
        default='',
        help='Base directory'
    )
    add_logging_arguments(parser)
    args = parser.parse_args()
    setup_logging(args.loglevel)

    logger.info('==== [0/8] Command line parameters ====')
    logger.info(f"Base directory    : {args.basedir or os.getcwd()}")
    logger.info(f"Loglevel          : {args.loglevel}")

    # set base directory
    if args.basedir:
        base_dir = os.path.abspath(args.basedir)
    else:
        base_dir = os.getcwd()
    ctx = RunContext(basedir=base_dir)

    # load system confguration
    conf_file = ctx.path('config/system_conf.json')
    try:
        with open(conf_file) as f:
            logger.info(f"Configuration file: {conf_file}")
            conf = json.loads(f.read())
    except Exception as e:
        logger.critical(f"failed to load configuration file: {e}")
        sys.exit(1)

    # load telegram chat id and bot token if configured
    if conf['notify'] == True:
        ta_file = ctx.path('config/telegram_conf.json')
        with open(ta_file) as f:
            logger.info(f"Telegram conf file: {ta_file}")
            ta_conf = json.loads(f.read())
        ctx.bot_token = ta_conf['bot_token']
        ctx.chat_id = ta_conf['chat_id']

    update_quotes(conf, ctx)

if __name__ == "__main__":
    main()
