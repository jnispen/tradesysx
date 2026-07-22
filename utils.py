''' Utility functions for backtesting and TA operations '''

import sys
import math
import os
import re
import json
import base64
import logging
import pandas as pd
import numpy as np
import seaborn as sns
import statistics as st
import requests

from datetime import datetime
from typing import Dict, List

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.transforms as mtransforms
from matplotlib.ticker import MaxNLocator

import talib as ta
import yfinance as yf

import statsmodels.api as sm
from scipy import stats

from weasyprint import HTML

from telegram import Bot
from telegram.constants import ParseMode

from tradesysx.strategy import Stoploss, TradingSignals
from tradesysx.tables import TotalTradesList, TradesTable
from tradesysx.context import RunContext, SystemStats
from tradesysx import report_plots as rp
from tradesysx import __version__

logger = logging.getLogger(__name__)

def _plain(text):
    return re.sub(r'<[^>]+>', '', text).encode('ascii', 'ignore').decode()

# for concat of empty dataframe
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

async def bot_signal_update(ctx, lastclose, telegram_df):
    ''' send daily signal overview to bot, one line per ticker with an emoji signal marker '''

    bot = Bot(token=ctx.bot_token)
    lastclose_str = lastclose.strftime('%a %d-%m-%Y')

    signal_emoji = {
        'ENTER':    '\U0001F7E2',  # green circle
        'EXIT':     '\U0001F535',  # blue circle
        'STOPLOSS': '\U0001F534',  # red circle
    }

    lines = []
    for _, row in telegram_df.iterrows():
        if row['Signal'] in signal_emoji:
            emoji = signal_emoji[row['Signal']]
        elif row['STLoss'] == 0:
            emoji = '⚫'  # black circle = not in a trade
        else:
            emoji = '⚪'  # white circle = in a trade, no signal today
        # a stop raised by the ladder today needs moving at the broker, so mark it
        sl_mark = '\U0001F53C ' if row.get('SLMoved', 0) > 0 else ''
        line = f"{emoji} <b>{row['Ticker']}</b> — Close {row['Close']:.2f} (SL {sl_mark}{row['STLoss']:.2f})"
        lines.append(line)

    msg = f"<b>{lastclose_str}</b>\n=============\n" + "\n".join(lines)
    logger.info("Telegram update:\n%s", _plain(msg))
    await bot.send_message(chat_id=ctx.chat_id, text=msg, parse_mode=ParseMode.HTML)

async def bot_signal_alert(ctx, lastclose, telegram_df):
    ''' send a summary message for tickers that have an active signal today, if any '''

    signal_emoji = {
        'ENTER':    '\U0001F7E2',  # green circle
        'EXIT':     '\U0001F535',  # blue circle
        'STOPLOSS': '\U0001F534',  # red circle
    }

    # a ladder-raised stop is actionable too (the resting stop order has to be
    # moved), so it alerts alongside the ENTER/EXIT/STOPLOSS signals
    sl_moved = telegram_df.get('SLMoved', pd.Series(0.0, index=telegram_df.index)) > 0
    signal_rows = telegram_df[telegram_df['Signal'].isin(signal_emoji) | sl_moved]
    if signal_rows.empty:
        return

    bot = Bot(token=ctx.bot_token)
    lastclose_str = lastclose.strftime('%a %d-%m-%Y')

    lines = []
    for _, row in signal_rows.iterrows():
        if row['Signal'] in signal_emoji:
            lines.append(f"{signal_emoji[row['Signal']]} <b>{row['Ticker']}</b> "
                         f"{row['Signal']} @ {row['Close']:.2f}")
        else:
            lines.append(f"\U0001F53C <b>{row['Ticker']}</b> SL RAISED to {row['STLoss']:.2f}")

    msg = f"\U0001F514 <b>Signal Alert</b>\n" + "\n".join(lines)
    logger.info("Telegram alert:\n%s", _plain(msg))
    await bot.send_message(chat_id=ctx.chat_id, text=msg, parse_mode=ParseMode.HTML)

def bot_summary_update(ctx, file_path):
    ''' send system summary to bot '''

    url = f'https://api.telegram.org/bot{ctx.bot_token}/sendDocument'
    with open(file_path, 'rb') as f:
        files = {'document': f}
        data  = {
            'chat_id': ctx.chat_id,
            'caption': '',
        }
        response = requests.post(url, data=data, files=files)
    return response

def get_history_data(ticker, period=None, start=None, end=None, interval='1d'):
    '''
    Available paramaters for the history() method are:
    period: data period to download (Either Use period parameter or use start and end) Valid periods are: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    interval: data interval (intraday data cannot extend last 60 days) Valid intervals are: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    start: If not using period - Download start date string (YYYY-MM-DD) or datetime.
    end: If not using period - Download end date string (YYYY-MM-DD) or datetime.
    prepost: Include Pre and Post market data in results? (Default is False)
    auto_adjust: Adjust all OHLC automatically? (Default is True)
    actions: Download stock dividends and stock splits events? (Default is True)

    For intraday data, use `period` and `interval` together (relative to the
    current date); `start`/`end` are not meaningful for intraday intervals.
    '''

    download_kwargs = {
        "tickers": ticker,
        "interval": interval,
        "auto_adjust": True,
        "multi_level_index": False,
    }
    if start is not None:
        download_kwargs["start"] = start
        if end is not None:
            download_kwargs["end"] = end
    elif period is not None:
        download_kwargs["period"] = period
    else:
        raise ValueError("Specify either `period` or `start`, or 'start' and `end`")
    
    raw_df = yf.download(**download_kwargs)
    if raw_df is None or raw_df.empty:
        raise RuntimeError("Download succeeded but returned an empty DataFrame")

    # intraday intervals are indexed as 'Datetime' rather than 'Date';
    # normalize so downstream code can always rely on a 'Date' column/index
    raw_df.index.name = 'Date'

    return raw_df

def data_range_spec(conf):
    ''' the subset of the configuration that determines which data is downloaded '''
    return {
        "start"   : conf.get("start"),
        "end"     : conf.get("end"),
        "period"  : conf.get("period"),
        "interval": conf.get("interval") or "1d",
    }

def write_data_manifest(conf, ctx):
    ''' records the date range the OHLC data on disk was downloaded for, so a later
        run with update_data=false can detect that the configuration has moved on '''
    manifest = {**data_range_spec(conf), "downloaded": datetime.now().isoformat(timespec='seconds')}
    with open(ctx.outpath('data', 'manifest.json'), 'w') as f:
        f.write(json.dumps(manifest, indent=2))

def check_data_manifest(conf, ctx):
    ''' warns when the OHLC data on disk was downloaded for a different date range
        than the one currently configured '''
    manifest_file = ctx.outpath('data', 'manifest.json')
    if not os.path.exists(manifest_file):
        logger.debug('no data manifest found - skipping date range check')
        return

    with open(manifest_file) as f:
        manifest = json.loads(f.read())

    spec = data_range_spec(conf)
    if {k: manifest.get(k) for k in spec} != spec:
        logger.warning('Data on disk was downloaded for a different date range!')
        logger.warning(f'  on disk: {format_date_range(manifest)} (downloaded {manifest.get("downloaded", "?")[:10]})')
        logger.warning(f'  config : {format_date_range(conf)}')
        logger.warning('  results are based on the on-disk range - set update_data=true to re-download')

def format_date_range(conf):
    ''' human-readable description of the configured download date range '''
    interval = conf.get("interval") or "1d"
    start, end = conf.get("start"), conf.get("end")

    if not start:
        return f'period {conf.get("period")} (interval {interval})'

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
    months = (end_ts.year - start_ts.year) * 12 + (end_ts.month - start_ts.month)
    if end_ts.day < start_ts.day:
        months -= 1
    span = ' '.join(p for p in (f'{months // 12}y' if months >= 12 else '',
                                f'{months % 12}m' if months % 12 else '') if p) or '<1m'

    return f'{start_ts.date()} -> {end_ts.date() if end else "today"} ({span}, interval {interval})'

def get_quotes_data(quotes, conf, outfile, ctx):
    ''' download the quotes data '''
    idx = 1
    for ticker, desc in quotes.items():
        logger.info(f'{idx} - {ticker}: {desc}')
        idx += 1

        interval = conf.get("interval", "1d")
        if conf.get("start") and conf.get("end"):
            dfr = get_history_data(ticker, start=conf["start"], end=conf["end"], interval=interval)
        elif conf.get("start"):
            dfr = get_history_data(ticker, start=conf["start"], interval=interval)
        else:
            dfr = get_history_data(ticker, conf["period"], interval=interval)

        dfr.to_csv(ctx.outpath('data',f"{ticker}_{outfile}"))

VALID_PLOT_INDICATORS = {'BB', 'SMA225', 'DON'}

def validate_plot_indicators(conf):
    ''' validates the conf['plot_indicators'] list against the known indicator names '''
    for name in conf.get('plot_indicators', []):
        if name not in VALID_PLOT_INDICATORS:
            logger.critical("The plot indicator '{}' does not exist! Valid options: {}".format(name, sorted(VALID_PLOT_INDICATORS)))
            sys.exit(1)

VALID_TA_CUSTOM = {'RSI', 'ADX', 'FI', 'OBV', 'MACD', 'DI', 'ATR', 'CCI', 'ROC', 'MFI'}

def validate_ta_custom(conf):
    ''' validates the conf['ta_custom'] list against the known indicator names '''
    for name in conf.get('ta_custom', []):
        if name not in VALID_TA_CUSTOM:
            logger.critical("The ta_custom indicator '{}' does not exist! Valid options: {}".format(name, sorted(VALID_TA_CUSTOM)))
            sys.exit(1)

VALID_REPORT_TYPES = {'short', 'full'}
VALID_REPORT_STYLES = {'classic', 'styled'}

def validate_report_style(conf):
    ''' validates conf['report_style'] (defaults to 'styled' if absent) '''
    report_style = conf.get('report_style', 'styled')
    if report_style not in VALID_REPORT_STYLES:
        logger.critical("The report_style '{}' does not exist! Valid options: {}".format(report_style, sorted(VALID_REPORT_STYLES)))
        sys.exit(1)

def validate_report_type(conf):
    ''' validates conf['report_type'] (defaults to 'short' if absent) '''
    report_type = conf.get('report_type', 'short')
    if report_type not in VALID_REPORT_TYPES:
        logger.critical("The report_type '{}' does not exist! Valid options: {}".format(report_type, sorted(VALID_REPORT_TYPES)))
        sys.exit(1)

def validate_gen_ta_custom(conf):
    ''' validates conf['gen_ta_custom'] (defaults to False if absent) against conf['ta_custom'] '''
    gen_ta_custom = conf.get('gen_ta_custom', False)
    if not isinstance(gen_ta_custom, bool):
        logger.critical("conf['gen_ta_custom'] must be a boolean, got: {}".format(gen_ta_custom))
        sys.exit(1)
    if gen_ta_custom and not conf.get('ta_custom'):
        logger.critical("conf['gen_ta_custom'] is true but conf['ta_custom'] is empty - nothing to plot")
        sys.exit(1)

def validate_strategy_conf(conf):
    ''' validates conf['enter']/conf['exit'] against the known strategies, up front '''
    if conf['enter'] not in TradingSignals.enter_str:
        logger.critical("The Enter strategy '{}' does not exist! Valid options: {}".format(conf['enter'], sorted(TradingSignals.enter_str)))
        sys.exit(1)
    if conf['exit'] not in TradingSignals.exit_str:
        logger.critical("The Exit strategy '{}' does not exist! Valid options: {}".format(conf['exit'], sorted(TradingSignals.exit_str)))
        sys.exit(1)

    # the moving-average periods must be ordered fast < slow, otherwise the
    # SMA/3EMA crossover conditions can never line up as intended
    if conf['sma_fast'] >= conf['sma_slow']:
        logger.warning(f"sma_fast ({conf['sma_fast']}) should be smaller than sma_slow ({conf['sma_slow']}) - the SMA strategy may not signal as intended")
    if not conf['ema_fast'] < conf['ema_mid'] < conf['ema_slow']:
        logger.warning(f"ema_fast/ema_mid/ema_slow ({conf['ema_fast']}/{conf['ema_mid']}/{conf['ema_slow']}) should be in ascending order - the 3EMA strategy may not signal as intended")

def add_technical_indicators(dframe, conf):
    ''' adds technical indicators as columns to the dataframe '''
    
    ### Trend Indicators ###
    
    # Simple Moving Average (SMA)
    dframe['SMAfast'] = ta.SMA(dframe['Close'], timeperiod=conf['sma_fast'])
    dframe['SMAslow'] = ta.SMA(dframe['Close'], timeperiod=conf['sma_slow'])
   
    # Bear/Bull indcator (stock above = Bull, Stock below = Bear)
    dframe['SMA225'] = ta.SMA(dframe['Close'], timeperiod=225)

    # Triple Moving Average (3EMA) (default 20 50 100)
    dframe['EMAfast'] = ta.EMA(dframe['Close'], timeperiod=conf['ema_fast'])
    dframe['EMAmid'] = ta.EMA(dframe['Close'], timeperiod=conf['ema_mid'])
    dframe['EMAslow'] = ta.EMA(dframe['Close'], timeperiod=conf['ema_slow'])

    # Moving Average Convergence Devergence (MACD)
    dframe['MACD'], dframe['MACDsig'], dframe['MACDhist'] = ta.MACD(dframe['Close'], fastperiod=conf['macd_fast'], slowperiod=conf['macd_slow'], signalperiod=conf['macd_signal'])

    ### Momentum Indicators ###

    # Relative Strength Index (RSI)
    dframe['RSI'] = ta.RSI(dframe['Close'], timeperiod=conf['rsi_time'])

    # Commodity Channel Index (CCI)
    dframe['CCI'] = ta.CCI(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=14)

    # Rate of change (ROC)
    dframe['ROC'] = ta.ROC(dframe['Close'], timeperiod=10)

    ### Volatility Indicators ###

    # Average True Range (ATR)
    dframe['ATR'] = ta.ATR(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=conf['atr_time'])

    # Bollinger Bands (SMA) (default settings)
    dframe['BBu'], dframe['BBm'], dframe['BBl'] = ta.BBANDS(dframe['Close'], timeperiod=20, matype=0)

    # Average Directional Movement Index (ADX)
    dframe['ADX'] = ta.ADX(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=14)

    # Directional Indicators (+DI and -DI)
    dframe['P_DI'] = ta.PLUS_DI(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=14)
    dframe['M_DI'] = ta.MINUS_DI(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=14)

    ### Volume Indicators ###

    # On Balance Volume (OBV)
    dframe['OBV'] = ta.OBV(dframe['Close'], dframe['Volume'])

    # Money Flow Index (MFI)
    dframe['MFI'] = ta.MFI(dframe['High'], dframe['Low'], dframe['Close'], dframe['Volume'], timeperiod=14)
    
    # Force Index (FI)
    dframe['FI'] = dframe['Close'].diff(13) * dframe['Volume']

    ### Trailing Exit ###

    # Chandelier Exit (CE)
    dframe['CEHigh'] = dframe['High'].rolling(22).max()
    atr22 = ta.ATR(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=22)
    dframe['CE']  = dframe['CEHigh'] - atr22 * 3
    dframe['CE2'] = dframe['CEHigh'] - atr22 * 2
    dframe['CE15'] = dframe['CEHigh'] - atr22 * 1.5
    dframe.drop(['CEHigh'], axis=1, inplace=True)

    # Donchian Channel (breakout entry/exit) — prior-day channels, exclude today
    dframe['DONup'] = dframe['High'].rolling(conf['donch_enter']).max().shift(1)
    dframe['DONdn'] = dframe['Low'].rolling(conf['donch_exit']).min().shift(1)

    return dframe

def get_rmean_qlabel(mean_R):
    label = ''
    if mean_R < -0.1:
        label = '(Poor)'
    if -0.1 <= mean_R < 0.1:
        label = '(Breakeven)'
    if 0.1 <= mean_R < 0.5:
        label = '(Normal)'
    if 0.5 <= mean_R < 1:
        label = '(Good)'
    if 1 <= mean_R < 2:
        label = '(Very Good)'
    if mean_R >= 2:
        label = '(Excellent)'
    return label

def get_system_qlabel(system_quality):
    label = ''
    if system_quality < 1.0:
        label = '(Poor)'
    if 1.0 <= system_quality < 2.0:
        label = '(Average)'
    if 2.0 <= system_quality < 3.0:
        label = '(Good)'
    if 3.0 <= system_quality < 5.0:
        label = '(Excellent)'
    if 5.0 <= system_quality < 7.0:
        label = '(Superb)'
    if system_quality >= 7.0:
        label = '(Holy Grail)'
    return label

def add_trading_signals(df, conf):
    ''' add ENTER, EXIT and InTrade signals '''

    # strategy classes
    signals = TradingSignals(conf)
    stloss  = Stoploss(conf)
    ladder_on = stloss.ladder_enabled()

    intrade     = 0
    stoploss    = 0.0
    risk_oneR   = 0.0
    entry_price = 0.0

    # trackers for MAE and MFE
    lowest_since_entry  = np.inf
    highest_since_entry = -np.inf

    # CEE/XR exit strategies read row['Rcur'] during iteration; this column
    # is otherwise only written via rcur_lst after the loop, so pre-create it
    # (stays NaN for the snapshot rows seen by df.iterrows(), matching the
    # original behaviour). Also preserves the original column ordering.
    df["Signal"] = None
    df['Rcur']   = np.nan

    n = len(df)
    signal_lst  = [None] * n
    rcur_lst    = [np.nan] * n
    enter_lst   = [np.nan] * n
    exit_lst    = [np.nan] * n
    mae_lst     = [np.nan] * n   # Maximum Adverse Excursion
    mfe_lst     = [np.nan] * n   # Maximum Favorable Excursion
    eratio_lst  = [np.nan] * n   # MFE/MAE
    intrade_lst = [0] * n
    stloss_lst  = [0.0] * n
    slmoved_lst = [0.0] * n   # amount the ladder raised the stop by, per day
    pricein_lst = [0.0] * n
    profit_lst  = [0.0] * n
    risk_lst    = [0.0] * n
    rmul_lst    = [np.nan] * n
    tlen_lst    = [np.nan] * n

    for i, (index, row) in enumerate(df.iterrows()):

        signal_lst[i] = "-"

        if intrade != 0:
            rcur_lst[i] = (row['Close'] - entry_price) / risk_oneR

            lowest_since_entry  = min(lowest_since_entry,  row['Close'])
            highest_since_entry = max(highest_since_entry, row['Close'])

            # MAE, MFE and E-Ratio, normalized by the trade's initial risk so
            # they read in R and sit on the same scale as Rmul. Both excursions
            # track Close (not High/Low) to match the rest of the system: signals
            # are only ever evaluated on the close, so a close-based excursion is
            # the move this system could actually have captured.
            if risk_oneR != 0:
                mae = (entry_price - lowest_since_entry) / risk_oneR
                mfe = (highest_since_entry - entry_price) / risk_oneR
                mae_lst[i] = mae
                mfe_lst[i] = mfe
                eratio_lst[i] = mfe / mae if mae != 0 else np.nan

                # ratchet the stop up to the highest ladder level MFE has
                # reached. Applied before the exit check below, so a close that
                # fades back through a locked level stops out on the same bar.
                # SLMoved records the size of the raise on the day it happens
                # (0.0 otherwise) so live trades can be flagged in the daily
                # Telegram update -- a raised stop has to be moved at the broker.
                if ladder_on:
                    new_stoploss = stloss.get_ladder_stoploss(entry_price, risk_oneR, mfe, stoploss)
                    if new_stoploss > stoploss:
                        slmoved_lst[i] = new_stoploss - stoploss
                        stoploss = new_stoploss
            else:
                mae_lst[i] = mfe_lst[i] = eratio_lst[i] = np.nan

        # ENTER signal
        if intrade == 0 and signals.check_enter_signal(row) == True:
            candidate_stoploss = stloss.get_stoploss(row)
            candidate_risk_oneR = row['Close'] - candidate_stoploss

            # skip entries where the stoploss can't be computed yet (e.g. an
            # ATR-based stoploss whose warm-up period ends a bar later than
            # the entry indicator's), which would otherwise enter a trade
            # with an undefined/zero risk and a NaN Rmul on exit
            if pd.notna(candidate_stoploss) and candidate_risk_oneR != 0:
                enter_lst[i] = row['Close']
                signal_lst[i] = "ENTER"

                intrade = 1
                stoploss = candidate_stoploss
                risk_oneR = candidate_risk_oneR
                entry_price = row["Close"]

                # update MFE and MAE
                lowest_since_entry  = entry_price
                highest_since_entry = entry_price

        # EXIT signal
        if intrade != 0 and (signals.check_exit_signal(row, intrade) or row['Close'] < stoploss):

            exit_lst[i] = row['Close']
            rmul_lst[i] = (row['Close'] - entry_price)/risk_oneR
            tlen_lst[i] = intrade

            if risk_oneR != 0:
                mae = (entry_price - lowest_since_entry) / risk_oneR
                mfe = (highest_since_entry - entry_price) / risk_oneR
                mae_lst[i] = mae
                mfe_lst[i] = mfe
                eratio_lst[i] = mfe / mae if mae != 0 else np.nan
            else:
                mae_lst[i] = mfe_lst[i] = eratio_lst[i] = np.nan

            signal_lst[i] = "STOPLOSS" if row['Close'] < stoploss else "EXIT"

            intrade     = 0
            stoploss    = 0.0
            entry_price = 0.0
            risk_oneR   = 0.0
            lowest_since_entry  = np.inf
            highest_since_entry = -np.inf

        intrade_lst[i] = int(intrade)
        stloss_lst[i]  = stoploss

        if intrade != 0:
            pricein_lst[i] = entry_price
            profit_lst[i]  = row['Close'] - entry_price
            risk_lst[i]    = risk_oneR
            intrade += 1
        else:
            pricein_lst[i] = 0.0
            profit_lst[i]  = 0.0
            risk_lst[i]    = 0.0

    df["Signal"] = signal_lst
    df['Rcur']   = rcur_lst
    df['Enter']  = enter_lst
    df['Exit']   = exit_lst
    df['MAE']    = mae_lst
    df['MFE']    = mfe_lst
    df["ERatio"] = eratio_lst
    df['InTrade'] = intrade_lst
    df['STLoss']  = stloss_lst
    df['SLMoved'] = slmoved_lst
    df['PriceIn'] = pricein_lst
    df['Profit']  = profit_lst
    df['Risk']    = risk_lst
    df['Rmul']    = rmul_lst
    df['TLen']    = tlen_lst

    return df

def generate_trading_table(df, ticker):
    ''' generate a dataframe containing all trades for a ticker '''

    trades_table = TradesTable()
    trades_lst = TotalTradesList()

    enter_mask = df['Enter'].notna()
    exit_mask  = df['Exit'].notna()

    enter_rows = df.loc[enter_mask]
    exit_rows  = df.loc[exit_mask]

    n_enter = len(enter_rows)
    n_exit  = len(exit_rows)

    # each EXIT is paired with the n-th ENTER (trades alternate strictly:
    # ENTER, EXIT, ENTER, EXIT, ... with at most one open trailing ENTER)
    price_in_arr = enter_rows['Enter'].to_numpy()[:n_exit]
    profit_arr = exit_rows['Close'].to_numpy() - price_in_arr

    enter_lst    = list(enter_rows.index)
    ticker_lst   = [ticker] * n_enter
    pricein_lst  = enter_rows['Enter'].round(2).tolist()
    risk_lst     = enter_rows['Risk'].round(2).tolist()

    exit_lst     = list(exit_rows.index)
    priceout_lst = exit_rows['Exit'].round(2).tolist()
    profit_lst   = np.round(profit_arr, 2).tolist()
    rmul_lst     = exit_rows['Rmul'].round(2).tolist()
    mae_lst      = exit_rows['MAE'].round(2).tolist()   # whole-trade MAE (R) at exit
    mfe_lst      = exit_rows['MFE'].round(2).tolist()   # whole-trade MFE (R) at exit
    duration_lst = exit_rows['TLen'].round(0).astype(int).tolist()
    signal_lst   = exit_rows['Signal'].tolist()
    lastclose_lst = ['-'] * n_exit

    date_lst   = [None] * (n_enter + n_exit)
    tck_lst    = [ticker] * (n_enter + n_exit)
    buy_lst    = [None] * (n_enter + n_exit)
    sell_lst   = [None] * (n_enter + n_exit)
    oneR_lst   = [None] * (n_enter + n_exit)
    pprofit_lst = [None] * (n_enter + n_exit)

    date_lst[0::2]    = list(enter_rows.index)
    buy_lst[0::2]     = enter_rows['Enter'].tolist()
    sell_lst[0::2]    = ['-'] * n_enter
    oneR_lst[0::2]    = enter_rows['Risk'].round(2).tolist()
    pprofit_lst[0::2] = ['-'] * n_enter

    date_lst[1::2]    = list(exit_rows.index)
    buy_lst[1::2]     = ['-'] * n_exit
    sell_lst[1::2]    = exit_rows['Exit'].tolist()
    oneR_lst[1::2]    = ['-'] * n_exit
    pprofit_lst[1::2] = profit_arr.tolist()

    # for open trades, fill in the empty fields (the open trade's ENTER is
    # already included in enter_rows above; only extend the exit-side lists)
    if df['InTrade'].iloc[-1] != 0:
        last_row = df.iloc[-1]
        exit_lst.append("-")
        priceout_lst.append("-")
        profit_lst.append(round(last_row['Profit'], 2))
        rmul_lst.append(round((last_row['Close']-last_row['PriceIn'])/last_row['Risk'], 2))
        mae_lst.append(round(last_row['MAE'], 2) if pd.notna(last_row['MAE']) else np.nan)
        mfe_lst.append(round(last_row['MFE'], 2) if pd.notna(last_row['MFE']) else np.nan)
        duration_lst.append(int(round(last_row['InTrade'], 0)))
        signal_lst.append(last_row['Signal'])
        lastclose_lst.append(round(last_row['Close'], 2))

    trades_table.df['Enter']    = enter_lst
    trades_table.df['Exit']     = exit_lst
    trades_table.df['Ticker']   = ticker_lst
    trades_table.df['PriceIn']  = pricein_lst
    trades_table.df['PriceOut'] = priceout_lst
    trades_table.df['Risk']     = risk_lst
    trades_table.df['Length']   = duration_lst
    trades_table.df['Rmul']     = rmul_lst
    trades_table.df['MAE']      = mae_lst
    trades_table.df['MFE']      = mfe_lst
    trades_table.df['Profit']   = profit_lst
    trades_table.df['Signal']   = signal_lst
    trades_table.df['LastClose'] = lastclose_lst

    trades_lst.df['Date']   = date_lst
    trades_lst.df['Ticker'] = tck_lst
    trades_lst.df['Enter']  = buy_lst
    trades_lst.df['Exit']   = sell_lst
    trades_lst.df['Risk']   = oneR_lst
    trades_lst.df['Profit'] = pprofit_lst

    return trades_table, trades_lst

def generate_system_stats(trades_df, trading_period, conf, ctx, stats):
    ''' compute system statistics and return summary info '''

    num_trades = trades_df.shape[0]
    len_trades = trading_period
    Rmax = trades_df['Rmul'].max()
    Rmin = trades_df['Rmul'].min()
    Ravg = trades_df['Rmul'].mean()
    Rstd = trades_df['Rmul'].std()

    # System Quality Number (SQN)
    SysQ = (Ravg / Rstd) * math.sqrt(len(trades_df)) if len(trades_df) < 100 else (Ravg / Rstd) * math.sqrt(100)
    stats.sqn = SysQ

    trades_lst = trades_df['Rmul'].tolist()
    times_lst  = trades_df['Length'].tolist()
    all_trades = list(zip(trades_lst, times_lst))

    # win/loss streaks over the actual trade sequence, in the same order the
    # report displays (trades_df is already sorted by entry date by
    # save_trades_table, which is the order shown in the trades-vs-R-multiple
    # plot), so the streaks reconcile with the runs a reader counts off that plot.
    max_win_streak, _ = win_streaks(trades_lst)
    max_loss_streak, _ = loss_streaks(trades_lst)
    stats.real_max_win_streak = int(max_win_streak)
    stats.real_max_loss_streak = int(max_loss_streak)

    pos_lst = [(r, t) for r, t in all_trades if r > 0]
    neg_lst = [(r, t) for r, t in all_trades if r <= 0]

    # safety checks
    if not pos_lst:  # avoid division by zero
        pos_mean_r = pos_mean_len = 0
    else:
        pos_sum_r, pos_sum_len = map(sum, zip(*pos_lst))
        pos_mean_r   = pos_sum_r / len(pos_lst)
        pos_mean_len = pos_sum_len / len(pos_lst)

    if not neg_lst:
        neg_mean_r = neg_mean_len = 0
    else:
        neg_sum_r, neg_sum_len = map(sum, zip(*neg_lst))
        neg_mean_r   = neg_sum_r / len(neg_lst)
        neg_mean_len = neg_sum_len / len(neg_lst)

    # calculate the Kelly criterion
    win_frac  = float(len(pos_lst) / num_trades)
    b = abs(pos_mean_r/neg_mean_r)
    kelly_criterion = win_frac - ((1 - win_frac) / b)
    stats.kelly_crit = kelly_criterion

    # store stats for use by later pipeline steps
    stats.trades_len = len_trades
    stats.trades_num = num_trades
    stats.win_rate = float(len(pos_lst)/num_trades * 100)

    data = {
        "Metric": [
            "Length (days)",
            "Trades total",
            "Trades/yr",
            "R maximum",
            "R minimum",
            "R stdev",
            "R mean",
            "System Quality",
            "R mean (win)", "R mean (loss)",
            "Length mean (win)", "Length mean (loss)",
            "Win Rate (%)",
            "Kelly criterion"
        ],
        "Value": [
            f"{len_trades}",
            f"{num_trades}",
            f"{num_trades / (len_trades/365):.2f}",
            f"{Rmax:,.2f}",
            f"{Rmin:,.2f}",
            f"{Rstd:,.2f}",
            f"{Ravg:,.2f} {get_rmean_qlabel(Ravg)}",
            f"{SysQ:,.2f} {get_system_qlabel(SysQ)}",
            f"{pos_mean_r:,.2f}",
            f"{neg_mean_r:,.2f}",
            f"{int(pos_mean_len)}",
            f"{int(neg_mean_len)}",
            f"{stats.win_rate:.0f}",
            f"{kelly_criterion:,.2f}"
        ]
    }

    stats_df = pd.DataFrame(data)

    stat_str = "\n".join([
        "=========== SYSTEM SUMMARY ===========",
        f"- Length (days)     : {len_trades}",
        f"- Trades total      : {num_trades}",
        f"- Trades/yr         : {num_trades / (len_trades/365):.2f}",
        f"- R maximum         : {Rmax:,.2f}",
        f"- R minimum         : {Rmin:,.2f}",
        f"- R stdev           : {Rstd:,.2f}",
        f"- R mean            : {Ravg:,.2f} {get_rmean_qlabel(Ravg)}",
        f"- System Quality    : {SysQ:,.2f} {get_system_qlabel(SysQ)}",
        f"- R mean (win)      : {pos_mean_r:,.2f}",
        f"- R mean (loss)     : {neg_mean_r:,.2f}",
        f"- Length mean (win) : {int(pos_mean_len)}",
        f"- Length mean (loss): {int(neg_mean_len)}",
        f"- Win Rate (%)      : {stats.win_rate:.0f}",
        f"- Kelly criterion   : {kelly_criterion:,.2f}",
    ])

    trades_plot(trades_lst, trades_df['Rmul30'].tolist(), stat_str, conf, ctx, stats)
    mae_scatter_plot(trades_df, conf, ctx)
    mfe_mae_scatter_plot(trades_df, conf, ctx)

    return stats_df

def fmt_conf_value(v):
    ''' render a config value for the report's config table: lists become
    comma-separated values, nested lists (e.g. ladder_levels) become bracketed
    groups, so [[1, 0], [2, 1]] reads "[1, 0], [2, 1]". '''

    if isinstance(v, list):
        return ", ".join(f"[{fmt_conf_value(i)}]" if isinstance(i, list)
                         else str(i) for i in v)
    return v

def _multi_column_table(items, columns, n_cols):
    ''' lay `items` (a list of row-tuples) out as `n_cols` side-by-side
    repetitions of `columns`, so a long list reads wide and short instead
    of a single tall column. '''

    chunk_size = math.ceil(len(items) / n_cols)
    parts = [
        pd.DataFrame(items[i:i + chunk_size], columns=columns)
        for i in range(0, len(items), chunk_size)
    ]
    max_len = max(len(part) for part in parts)
    parts = [part.reindex(range(max_len)).fillna("") for part in parts]
    return pd.concat(parts, axis=1)

def generate_summary_report(stat_df, conf, quotes, ctx, stats, full=False):
    ''' generate a pdf report with system summary, configuration and figures.

    `conf` is the system config dict and `quotes` is the ticker -> description
    dict (rendered as tables). If `full` is True, the report also includes
    every ticker's plot, at the same size as the other figures. '''

    stat_html = stat_df.to_html(border=0, index=False, classes="summary-table")

    # trading-simulation summary, rendered in the same style as the system
    # summary table and placed directly under the balance plot. Labels and value
    # formatting mirror the log lines emitted by do_balance_simulation (the
    # "Total invested" closure-check line is intentionally left out here).
    balance_data = {
        "Metric": [
            "Starting balance",
            "Open trades closed",
            "Average investment",
            "Average value",
            "Average balance",
            "Average risk ($)",
            "Average risk (%)",
            "Final balance",
            "CAGR",
            "Sharpe ratio",
            "MAR ratio",
            "Average monthly return",
            "Longest drawdown",
        ],
        "Value": [
            f"{float(conf['balance']):,.2f}",
            f"{stats.open_trades_closed}",
            f"{stats.avg_invested:,.2f}",
            f"{stats.avg_value:,.2f}",
            f"{stats.avg_balance:,.2f}",
            f"{stats.avg_risk:,.2f}",
            f"{stats.avg_risk_per:.2f}",
            f"{stats.final_balance:,.2f}",
            f"{stats.cagr:.1%}",
            f"{stats.sharpe_ratio:.2f}" if stats.sharpe_ratio is not None else "-",
            f"{stats.mar_ratio:.2f}" if stats.mar_ratio is not None else "-",
            f"{stats.avg_month:,.2f}",
            f"{stats.max_dd_recovery} days",
        ],
    }
    balance_html = pd.DataFrame(balance_data).to_html(border=0, index=False, classes="summary-table")

    conf_items = [(k, fmt_conf_value(v)) for k, v in conf.items()]
    conf_table = _multi_column_table(conf_items, ["Key", "Value"], n_cols=2)
    conf_html = conf_table.to_html(border=0, index=False, classes="full-table")

    quotes_table = _multi_column_table(list(quotes.items()), ["Ticker", "Description"], n_cols=2)
    quotes_html = quotes_table.to_html(border=0, index=False, classes="quotes-table")

    benchmark_enabled = conf.get('benchmark', True)
    bm_ticker = conf.get('bm_ticker', 'URTH')

    # when the benchmark is the equal-weight buy-and-hold basket of the whole
    # quote list, render its per-ticker breakdown as a table (it takes the slot
    # the single-ticker benchmark plot would otherwise occupy). The closing
    # "Total" row states the starting amount, the aggregate ending value and the
    # CAGR - the same figure shown on the Monte Carlo plot's HODL label.
    benchmark_table_html = ""
    if benchmark_enabled and bm_ticker == 'quote-lst':
        if ctx.benchmark_df is None:
            ctx.benchmark_df = _build_basket_benchmark_df(conf, ctx)
        bm_df = ctx.benchmark_df
        invested_total = bm_df['Invested'].sum()
        val_out = bm_df['Net Value (incl. fee)'].sum()
        cagr = ann_return(conf['balance'], val_out, stats.trades_len / 365) if stats.trades_len else 0.0
        disp = bm_df.copy()
        for col in ['Buy', 'Invested', 'Units', 'Sell', 'Net Value (incl. fee)']:
            disp[col] = disp[col].map(lambda x: f"{x:,.2f}")
        total_row = {'#': '', 'Ticker': 'Total', 'Buy': '', 'Invested': f"{invested_total:,.2f}",
                     'Units': '', 'Sell': '', 'Net Value (incl. fee)': f"{val_out:,.2f}"}
        cagr_row = {'#': '', 'Ticker': '', 'Buy': '', 'Invested': '',
                    'Units': '', 'Sell': 'CAGR', 'Net Value (incl. fee)': f"{cagr:.1%}"}
        disp = pd.concat([disp, pd.DataFrame([total_row, cagr_row])], ignore_index=True)
        # sub-header row carrying the basket's buy/sell dates below the Buy/Sell
        # headers, so the report shows the timeframe the benchmark spans
        disp.columns = pd.MultiIndex.from_tuples(
            [('#', ''), ('Ticker', ''), ('Buy', f"({bm_df.attrs.get('buy_date', '')})"),
             ('Invested', ''), ('Units', ''), ('Sell', f"({bm_df.attrs.get('sell_date', '')})"),
             ('Net Value (incl. fee)', '')])
        bm_table = disp.to_html(border=0, index=False, classes="benchmark-table")
        quotefile = os.path.basename(conf.get('quotefile', ''))
        benchmark_table_html = f"""
        <h2 style="page-break-before: always;">Benchmark (buy-and-hold basket &ndash; {quotefile})</h2>
        {bm_table}
        """

    fig_width = 650

    fig_a = ctx.outpath("images/system_trades_plot.png")
    fig_b = ctx.outpath("images/system_trades_dist_plot.png")
    fig_c = ctx.outpath("images/balance_plot.png")
    fig_d = ctx.outpath("images/monte_carlo_plot.png")
    fig_e_html = ""
    if benchmark_enabled and bm_ticker != 'quote-lst':
        fig_e = ctx.outpath("plots", f"{bm_ticker}_plot.png")
        fig_e_html = f"""<img src="file://{fig_e}" style="width:{fig_width}px">"""

        # single-ticker buy-and-hold breakdown, shown below the benchmark plot -
        # the whole account is put into the one ticker, fee-less, so the "Value"
        # column equals the HODL figure on the Monte Carlo plot by construction.
        single_df = pd.read_csv(ctx.outpath('data', f"{bm_ticker}_ohlc_raw.csv"))
        single_df = single_df.dropna(subset=['Close'])
        price_in = single_df['Close'].iloc[0]
        price_out = single_df['Close'].iloc[-1]
        buy_date = str(single_df['Date'].iloc[0])
        sell_date = str(single_df['Date'].iloc[-1])
        invested = float(conf['balance'])
        units = invested / price_in
        value = units * price_out
        cagr = ann_return(conf['balance'], value, stats.trades_len / 365) if stats.trades_len else 0.0
        data_row = {'Ticker': bm_ticker, 'Buy': f"{price_in:,.2f}", 'Invested': f"{invested:,.2f}",
                    'Units': f"{units:,.2f}", 'Sell': f"{price_out:,.2f}", 'Value': f"{value:,.2f}"}
        cagr_row = {'Ticker': '', 'Buy': '', 'Invested': '', 'Units': '', 'Sell': 'CAGR',
                    'Value': f"{cagr:.1%}"}
        single_disp = pd.DataFrame([data_row, cagr_row],
                                   columns=['Ticker', 'Buy', 'Invested', 'Units', 'Sell', 'Value'])
        # sub-header row carrying the buy/sell dates below the Buy/Sell headers,
        # so the report shows the timeframe the benchmark spans
        single_disp.columns = pd.MultiIndex.from_tuples(
            [('Ticker', ''), ('Buy', f"({buy_date})"), ('Invested', ''),
             ('Units', ''), ('Sell', f"({sell_date})"), ('Value', '')])
        single_table = single_disp.to_html(border=0, index=False, classes="benchmark-single")
        benchmark_table_html = f"""
        <h2>Benchmark (buy-and-hold &ndash; {bm_ticker})</h2>
        {single_table}
        """

    ticker_section = ""
    if full:
        rows = "".join(
            f"""<img src="file://{ctx.outpath('plots', f'{ticker}_plot.png')}" style="width:{fig_width}px">"""
            for ticker in quotes
        )
        ticker_section = f"""
        <h2>Ticker Plots</h2>
        {rows}
        """

    html_content = f"""
    <html>
    <head>
        <style>
            @page {{
                size: A4 Portrait;
                margin: 1.5cm;
            }}
            body {{
                font-family: monospace;
                font-size: 12px;
                line-height: 1.4;
            }}
            {table_style_css(14)}
            th, td {{ text-align: left; }}
            table.compact-table {{ width: auto; table-layout: auto; }}
            table.summary-table {{ width: 46%; table-layout: fixed; }}
            table.summary-table th:nth-child(odd), table.summary-table td:nth-child(odd) {{ width: 50%; }}
            table.summary-table th:nth-child(even), table.summary-table td:nth-child(even) {{ width: 50%; }}
            table.full-table {{ width: 92%; table-layout: fixed; }}
            table.full-table th:nth-child(odd), table.full-table td:nth-child(odd) {{ width: 22%; }}
            table.full-table th:nth-child(even), table.full-table td:nth-child(even) {{ width: 28%; }}
            table.quotes-table {{ width: 92%; table-layout: fixed; }}
            table.quotes-table th:nth-child(odd), table.quotes-table td:nth-child(odd) {{ width: 15%; }}
            table.quotes-table th:nth-child(even), table.quotes-table td:nth-child(even) {{ width: 35%; }}
            table.benchmark-table {{ width: 92%; table-layout: auto; }}
            table.benchmark-table tr:nth-last-child(-n+2) {{ font-weight: bold; }}
            table.benchmark-single {{ width: 92%; table-layout: auto; }}
            table.benchmark-single tr:nth-last-child(-n+1) {{ font-weight: bold; }}
            table.benchmark-table thead tr:nth-child(2) th,
            table.benchmark-single thead tr:nth-child(2) th {{ font-size: 10px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2>System Configuration Parameters</h2>
        {conf_html}
        <h2>Quotes List</h2>
        {quotes_html}
        <h2>System Summary</h2>
        {stat_html}

        <div style="height: 16px;"></div>
        <img src="file://{fig_a}" style="width:{fig_width}px">
        <img src="file://{fig_b}" style="width:{fig_width}px">
        <img src="file://{fig_c}" style="width:{fig_width}px">
        <div style="height: 16px;"></div>
        <h2>Trading Simulation</h2>
        {balance_html}
        <div style="height: 16px;"></div>
        <img src="file://{fig_d}" style="width:{fig_width}px">
        {fig_e_html}
        {benchmark_table_html}

        {ticker_section}
    </body>
    </html>
    """

    # same filename for short and full (full just appends the ticker plots)
    output_path = ctx.outpath("system_summary.pdf")
    HTML(string=html_content).write_pdf(output_path)

    if full:
        logger.info(f"Report saved: {output_path}")

def _data_uri(path):
    ''' read an image file and return it as a base64 data-URI (keeps the styled
    report self-contained: one HTML file, no external assets). '''
    try:
        with open(path, 'rb') as f:
            enc = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{enc}"
    except OSError:
        return ""


def _logo_data_uri():
    ''' the TradeSysX icon as a base64 SVG data-URI for the styled report header
    (keeps the report self-contained). Read relative to this module so it works
    regardless of basedir/cwd; returns "" if the asset is unavailable. '''
    path = os.path.join(os.path.dirname(__file__), 'docs', 'examples', 'tradesysx-icon.svg')
    try:
        with open(path, 'rb') as f:
            enc = base64.b64encode(f.read()).decode()
        return f"data:image/svg+xml;base64,{enc}"
    except OSError:
        return ""


def _fmt_signed_r(x):
    ''' R-multiple with an explicit sign and a true minus sign. '''
    return (f"+{x:.2f}" if x >= 0 else f"−{abs(x):.2f}")


def generate_styled_report(stat_df, conf, quotes, ctx, stats, full=False):
    ''' generate the "styled" system report (report_style="styled").

    Produces two outputs from one WeasyPrint-safe template: the PDF at
    out/system_summary.pdf and a self-contained HTML at
    out/html/system_summary.html (charts embedded as base64 data-URIs). Layout
    follows the report-styling skill: header, KPI cards, strategy-vs-benchmark
    bars, trade statistics, charts, Monte Carlo, then the config/quotes
    appendix, with a footer on every page. '''

    from tradesysx.report_style import ACCENT, NEUTRAL, POS, NEG, GRID, TEXT, TEXT2, IND_GOLD

    # ---- pull numbers out of the system-summary frame + stats ----
    sd = dict(zip(stat_df['Metric'], stat_df['Value']))

    def num(key):
        try:
            return float(str(sd.get(key, '')).split()[0].replace(',', ''))
        except (ValueError, IndexError):
            return None

    balance = float(conf['balance'])
    trades_num = stats.trades_num or int(num('Trades total') or 0)
    trades_yr = num('Trades/yr')
    rmean = num('R mean'); rmean_win = num('R mean (win)'); rmean_loss = num('R mean (loss)')
    rmax = num('R maximum'); rmin = num('R minimum'); rstd = num('R stdev')
    kelly = num('Kelly criterion')
    len_win = num('Length mean (win)'); len_loss = num('Length mean (loss)')
    winners = round(stats.win_rate / 100.0 * trades_num) if trades_num else 0
    losers = trades_num - winners

    # ---- benchmark (works for both single-ticker and quote-lst basket modes) ----
    benchmark_enabled = conf.get('benchmark', True)
    bm_ticker = conf.get('bm_ticker', 'URTH')
    if bm_ticker == 'quote-lst':
        # the basket has no single-ticker description; bm_desc (e.g. a leftover
        # ETF name) would be misleading. The quote file is shown in the benchmark
        # table, so keep the header label short.
        bm_desc = "buy-and-hold basket"
    else:
        bm_desc = conf.get('bm_desc') or bm_ticker
    bm_label = "equal-weight basket" if bm_ticker == 'quote-lst' else bm_ticker
    val_out = _get_benchmark_result(conf, ctx) if benchmark_enabled else None
    bm_cagr = ann_return(balance, val_out, stats.trades_len / 365) if (val_out and stats.trades_len) else None
    cagr_delta = (stats.cagr - bm_cagr) * 100 if bm_cagr is not None else None
    # max drawdown over the holding period, for the strategy equity curve and
    # the buy-and-hold benchmark (both single-ticker and basket modes)
    strat_dd = _strategy_drawdown_pct(ctx)
    bm_dd = _benchmark_drawdown_pct(conf, ctx) if benchmark_enabled else None

    # ---- header date range (from the saved trades table) ----
    date_range = ""
    try:
        _tt = pd.read_csv(ctx.outpath('tables', 'trades_table.csv'))
        _d0 = pd.to_datetime(_tt['Enter']).min()
        _d1 = pd.to_datetime(_tt['Exit']).max()
        date_range = f"{_d0.strftime('%b %Y')} – {_d1.strftime('%b %Y')}"
    except Exception:
        date_range = f"{stats.trades_len} days"

    gen_ts = datetime.now().strftime('%d %b %Y, %H:%M')
    sqn_badge = get_system_qlabel(stats.sqn).strip('()')
    strategy_desc = f"{conf['enter']} enter / {conf['exit']} exit, long only"

    # ---- KPI cards ----
    def kpi(label, value, ctx_line, ctx_cls=""):
        return (f'<div class="kpi"><p class="lbl">{label}</p>'
                f'<p class="val">{value}</p>'
                f'<p class="ctx {ctx_cls}">{ctx_line}</p></div>')

    if cagr_delta is not None:
        delta_cls = "up" if cagr_delta >= 0 else "down"
        delta_txt = f"{'+' if cagr_delta >= 0 else '−'}{abs(cagr_delta):.1f} pts vs benchmark"
    else:
        delta_cls, delta_txt = "", "annualized"
    cards = [
        kpi("CAGR", f"{stats.cagr:.1%}", delta_txt, delta_cls),
        kpi("Final balance", f"${stats.final_balance:,.0f}", f"from ${balance:,.0f} start"),
        kpi("System quality (SQN)", f"{stats.sqn:.2f}<span class=\"badge\">{sqn_badge}</span>", "Van Tharp scale"),
        kpi("Win rate", f"{stats.win_rate:.0f}%",
            f"{trades_num} trades" + (f" &middot; ~{trades_yr:.0f}/yr" if trades_yr else "")),
        kpi("Max drawdown", f"{strat_dd:.1f}%" if strat_dd is not None else "&ndash;",
            "strategy equity, peak-to-trough"),
        kpi("R mean", _fmt_signed_r(rmean) if rmean is not None else "&ndash;",
            (f'avg win <span class="pos">{_fmt_signed_r(rmean_win)}</span> '
             f'&middot; avg loss <span class="neg">{_fmt_signed_r(rmean_loss)}</span>'
             if (rmean_win is not None and rmean_loss is not None) else "per trade")),
    ]
    kpi_html = "".join(cards)

    # ---- strategy vs benchmark bars ----
    def _dd_cell(v):
        val = f"−{v:.1f}%" if v is not None else "&ndash;"
        return f'<div class="maxdd">{val}<br><span class="mut">Max DD</span></div>'

    benchmark_bars = ""
    if val_out is not None:
        m = max(stats.final_balance, val_out) or 1.0
        sp = stats.final_balance / m * 100
        bp = val_out / m * 100
        benchmark_bars = f"""
        <div class="cmp">
          <div class="cmprow">
            <div class="name">Strategy<small>{conf['enter']}, long only</small></div>
            <div class="track"><div class="bar s" style="width:{sp:.0f}%">${stats.final_balance:,.0f}</div></div>
            <div class="cagr">{stats.cagr:.1%}<br><span class="mut">CAGR</span></div>
            {_dd_cell(strat_dd)}
          </div>
          <div class="cmprow">
            <div class="name">Buy &amp; hold<small>{bm_label}</small></div>
            <div class="track"><div class="bar b" style="width:{bp:.0f}%">${val_out:,.0f}</div></div>
            <div class="cagr">{f'{bm_cagr:.1%}' if bm_cagr is not None else '&ndash;'}<br><span class="mut">CAGR</span></div>
            {_dd_cell(bm_dd)}
          </div>
        </div>
        <p class="cap">Max DD is the maximum peak-to-trough decline in value over the holding period.</p>"""

    # ---- trade statistics tables ----
    def row(k, v, cls=""):
        return f"<tr><td class='k'>{k}</td><td class='num {cls}'>{v}</td></tr>"

    def ratio_class(val):
        ''' colour class for the Sharpe/MAR ratios: red < 0.5, orange 0.5-1.0,
        green >= 1.0. Compares the value rounded to the 2 decimals shown, so a
        figure that displays as 1.00 reads as green. '''
        if val is None:
            return ""
        r = round(val, 2)
        return "neg" if r < 0.5 else "warn" if r < 1.0 else "pos"

    stats_left = "".join([
        row("Trades", trades_num),
        row("Winners / losers", f"{winners} / {losers}"),
        row("Win rate", f"{stats.win_rate:.1f}%"),
        row("R mean", _fmt_signed_r(rmean) if rmean is not None else "&ndash;", "pos" if (rmean or 0) >= 0 else "neg"),
        row("R standard deviation", f"{rstd:.2f}" if rstd is not None else "&ndash;"),
        row("R mean (win)", _fmt_signed_r(rmean_win) if rmean_win is not None else "&ndash;", "pos"),
        row("R mean (loss)", _fmt_signed_r(rmean_loss) if rmean_loss is not None else "&ndash;", "neg"),
    ])
    stats_right = "".join([
        row("Best trade", _fmt_signed_r(rmax) + " R" if rmax is not None else "&ndash;", "pos"),
        row("Worst trade", _fmt_signed_r(rmin) + " R" if rmin is not None else "&ndash;", "neg"),
        row("Avg holding (win)", f"{len_win:.0f} days" if len_win is not None else "&ndash;"),
        row("Avg holding (loss)", f"{len_loss:.0f} days" if len_loss is not None else "&ndash;"),
        row("Max win streak", f"{stats.real_max_win_streak} trades"),
        row("Max loss streak", f"{stats.real_max_loss_streak} trades"),
        row("Kelly criterion", f"{kelly:.2f}" if kelly is not None else "&ndash;"),
    ])

    # trading-simulation summary (mirrors the classic report's balance table),
    # split across two columns: the simulation inputs/outputs on the left, the
    # annualized/derived performance ratios and their supporting figures on the right
    sim_rows_left = "".join([
        row("Starting balance", f"${balance:,.0f}"),
        row("Position sizing", rp.pos_sizing_label(conf)),
        row("Open trades closed", stats.open_trades_closed),
        row("Average investment", f"${stats.avg_invested:,.0f}"),
        row("Average equity value", f"${stats.avg_value:,.0f}"),
        row("Average cash balance", f"${stats.avg_balance:,.0f}"),
        row("Average risk", f"${stats.avg_risk:,.2f} ({stats.avg_risk_per:.2f}%)"),
    ])
    dd_period = (f"{stats.max_dd_recovery_from} &rarr; {stats.max_dd_recovery_to}"
                 if stats.max_dd_recovery_from != "-" else "&ndash;")
    sim_rows_right = "".join([
        row("Final balance", f"${stats.final_balance:,.0f}"),
        row("Average monthly return", f"${stats.avg_month:,.0f}"),
        row("Longest drawdown", f"{stats.max_dd_recovery} days"),
        row("", dd_period),
        row("CAGR", f"{stats.cagr:.1%}",
            ("pos" if stats.cagr >= bm_cagr else "neg") if bm_cagr is not None
            else ("pos" if stats.cagr >= 0 else "neg")),
        row("Sharpe ratio", f"{stats.sharpe_ratio:.2f}" if stats.sharpe_ratio is not None else "&ndash;",
            ratio_class(stats.sharpe_ratio)),
        row("MAR ratio", f"{stats.mar_ratio:.2f}" if stats.mar_ratio is not None else "&ndash;",
            ratio_class(stats.mar_ratio)),
    ])

    # ---- selected trades (largest + smallest outcomes) ----
    trades_table_html = ""
    try:
        tt = pd.read_csv(ctx.outpath('tables', 'trades_table.csv'))
        tt['PriceIn'] = pd.to_numeric(tt['PriceIn'], errors='coerce')
        tt['Length'] = pd.to_numeric(tt['Length'], errors='coerce')
        tt['Rmul'] = pd.to_numeric(tt['Rmul'], errors='coerce')
        # still-open trades have no realised Exit/PriceOut; they are valued at
        # LastClose and that unrealised R is what the system stats also count
        # (e.g. the "Best trade" KPI), so include them here instead of dropping
        # them - otherwise the table can miss the largest/smallest R-multiple
        tt['OutPrice'] = pd.to_numeric(tt['PriceOut'], errors='coerce').fillna(
            pd.to_numeric(tt['LastClose'], errors='coerce'))
        tt['IsOpen'] = tt['Exit'].astype(str).str.strip().eq('-')
        ttc = tt.dropna(subset=['Rmul', 'Length', 'OutPrice'])
        sel = pd.concat([ttc.nlargest(4, 'Rmul'), ttc.nsmallest(3, 'Rmul')])
        rows_html = ""
        for _, r in sel.iterrows():
            cls = "pos" if r['Rmul'] >= 0 else "neg"
            if r['IsOpen']:
                reason = "open"
            elif r['Signal'] == 'STOPLOSS':
                reason = "stop loss"
            else:
                reason = "exit signal"
            exit_txt = "&mdash;" if r['IsOpen'] else str(r['Exit'])[:10]
            rows_html += (
                f"<tr><td>{r['Ticker']}</td><td class='num'>{str(r['Enter'])[:10]}</td>"
                f"<td class='num'>{exit_txt}</td>"
                f"<td class='num'>{float(r['PriceIn']):,.2f}</td>"
                f"<td class='num'>{float(r['OutPrice']):,.2f}</td>"
                f"<td class='num'>{int(r['Length'])}</td>"
                f"<td class='num {cls}'>{_fmt_signed_r(float(r['Rmul']))}</td>"
                f"<td class='tag'>{reason}</td></tr>")
        trades_table_html = f"""
        <table class="wide">
          <thead><tr><th>Ticker</th><th class="num">Enter</th><th class="num">Exit</th>
          <th class="num">In</th><th class="num">Out</th><th class="num">Days</th>
          <th class="num">R-multiple</th><th>Exit reason</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
        <p class="cap">Selected trades &mdash; four largest and three smallest outcomes.</p>"""
    except Exception as e:
        logger.debug(f"styled report: skipping selected-trades table ({e})")

    # ---- charts (embedded as data-URIs) ----
    img_equity = _data_uri(ctx.outpath('images', 'balance_plot.png'))
    img_bars = _data_uri(ctx.outpath('images', 'system_trades_plot.png'))
    img_dist = _data_uri(ctx.outpath('images', 'system_trades_dist_plot.png'))
    img_mc = _data_uri(ctx.outpath('images', 'monte_carlo_plot.png'))
    img_mae_r = _data_uri(ctx.outpath('images', 'mae_scatter_plot.png'))
    img_mfe_mae = _data_uri(ctx.outpath('images', 'mfe_mae_scatter_plot.png'))
    img_equity_detail = _data_uri(ctx.outpath('images', 'equity_plot.png'))
    img_monthly_dist = _data_uri(ctx.outpath('images', 'monthly_dist_plot.png'))

    # ---- appendix: MFE/MAE scatters (generated in generate_system_stats,
    # so both PNGs already exist by report time; each is included only if present)
    mfe_mae_figs = ""
    if img_mae_r:
        mfe_mae_figs += (f'<h3>R-multiple vs. MAE</h3>'
                         f'<figure><img src="{img_mae_r}" alt="MAE vs R-multiple per trade">'
                         f'<figcaption>Each closed trade\'s MAE (how far '
                         f'it ran against you, in R) versus its realised R-multiple. The shaded '
                         f'band (MAE &gt; 1 R) is the stopped-out region.</figcaption></figure>')
    if img_mfe_mae:
        mfe_mae_figs += (f'<h3>MFE vs. MAE and Efficiency Ratio</h3>'
                         f'<figure><img src="{img_mfe_mae}" alt="MFE vs MAE per trade">'
                         f'<figcaption>MFE (how far each trade ran for you) against MAE, both in R, '
                         f'coloured by the share of the peak kept at exit (the efficiency '
                         f'ratio).</figcaption></figure>')
    # one .keep block so the heading and both scatters stay on a single page
    mfe_mae_title = "Appendix &mdash; scatterplots"
    mfe_mae_section = (f'<div class="keep mfemae"><h2 id="sec-mfemae">{mfe_mae_title}</h2>'
                       f'{mfe_mae_figs}</div>' if mfe_mae_figs else "")

    mc_section = ""
    if conf.get('montecarlo', True) and img_mc:
        # in a short report the preceding sections no longer fill their pages, so
        # start the simulation on a clean page rather than let it trail a part-full one
        mc_pbreak = '' if full else ' class="pbreak"'
        mc_section = f"""
        <h2 id="sec-montecarlo"{mc_pbreak}>Monte Carlo simulation</h2>
        <p>Resampling the realised R-multiples over {conf.get('iterations', 0):,} randomised
        trade sequences estimates the spread of outcomes the system could produce from the
        same edge in a different order. Each simulated run is a sequence of complete, closed
        trades applied in order, each risking the per-trade amount shown in the table below &mdash;
        the average dollar risk from the account-value simulation.</p>
        <figure style="margin-top:18px"><img src="{img_mc}" alt="Monte Carlo simulated equity paths">
        <figcaption>Simulated equity paths (a subset shown) with the median outcome in
        purple and the buy-and-hold benchmark as the dashed grey line.</figcaption></figure>
        <div class="statgrid">
          <table><tbody>{row("Iterations", f"{conf.get('iterations', 0):,}")}
          {row("Risk per trade", f"{stats.avg_risk / balance * 100:.2f}%")}
          {row("Avg loss streak", f"{stats.avg_loss_streak:.0f} trades")}
          {row("Max loss streak", f"{stats.max_loss_streak} trades")}</tbody></table>
          <table><tbody>{row("Max drawdown (peak-to-trough)", f"{stats.max_drawdown:.1f}%", "neg")}
          {row("Minimum ending balance", f"${stats.min_end_balance:,.0f}")}
          {row("System quality (sim / real)", f"{stats.sqn_sampled:.2f} / {stats.sqn:.2f}")}
          {row("R-average (sim / real)", f"{stats.rmul_avg_sampled:.2f} / {rmean:.2f}" if rmean is not None else "&ndash;")}</tbody></table>
        </div>"""

    # ---- benchmark detail table (both single-ticker and quote-lst basket) ----
    benchmark_detail = ""
    if benchmark_enabled:
        cagr_cell = f"{bm_cagr:.1%}" if bm_cagr is not None else "&ndash;"
        if bm_ticker == 'quote-lst':
            if ctx.benchmark_df is None:
                ctx.benchmark_df = _build_basket_benchmark_df(conf, ctx)
            bdf = ctx.benchmark_df
            invested_total = bdf['Invested'].sum()
            buy_d = bdf.attrs.get('buy_date', ''); sell_d = bdf.attrs.get('sell_date', '')
            brows = "".join(
                f"<tr><td class='num'>{int(r['#'])}</td><td>{r['Ticker']}</td>"
                f"<td class='num'>{r['Buy']:,.2f}</td><td class='num'>{r['Invested']:,.2f}</td>"
                f"<td class='num'>{r['Units']:,.2f}</td><td class='num'>{r['Sell']:,.2f}</td>"
                f"<td class='num'>{r['Net Value (incl. fee)']:,.2f}</td></tr>"
                for _, r in bdf.iterrows())
            brows += (f"<tr class='tot'><td></td><td>Total</td><td></td>"
                      f"<td class='num'>{invested_total:,.2f}</td><td></td><td></td>"
                      f"<td class='num'>{val_out:,.2f}</td></tr>"
                      f"<tr class='tot'><td colspan='6' class='num'>CAGR</td><td class='num'>{cagr_cell}</td></tr>")
            quotefile = os.path.basename(conf.get('quotefile', ''))
            bm_detail_title = f"Benchmark &mdash; buy-and-hold basket ({quotefile})"
            benchmark_detail = f"""
            <h2 id="sec-benchmark-detail" class="pbreak">{bm_detail_title}</h2>
            <table class="wide"><thead><tr>
              <th class="num">#</th><th>Ticker</th>
              <th class="num">Buy<span class="subd">{buy_d}</span></th>
              <th class="num">Invested</th><th class="num">Units</th>
              <th class="num">Sell<span class="subd">{sell_d}</span></th>
              <th class="num">Net value</th></tr></thead>
              <tbody>{brows}</tbody></table>"""
        else:
            sdf = pd.read_csv(ctx.outpath('data', f"{bm_ticker}_ohlc_raw.csv")).dropna(subset=['Close'])
            p_in = sdf['Close'].iloc[0]; p_out = sdf['Close'].iloc[-1]
            buy_d = str(sdf['Date'].iloc[0])[:10]; sell_d = str(sdf['Date'].iloc[-1])[:10]
            units = balance / p_in; value = units * p_out
            _bm_head = f"{bm_desc} &ndash; {bm_ticker}" if bm_desc and bm_desc != bm_ticker else bm_ticker
            # single-ticker benchmark price chart (mirrors the classic report's
            # fig_e), embedded above its buy-and-hold breakdown table
            img_bm = _data_uri(ctx.outpath('plots', f'{bm_ticker}_plot.png'))
            bm_figure = (f"""<figure style="margin-bottom:26px"><img src="{img_bm}" alt="{bm_ticker} benchmark close price">
            <figcaption>{_bm_head} close price over the holding period, the buy-and-hold
            benchmark reference.</figcaption></figure>""" if img_bm else "")
            bm_detail_title = f"Benchmark &mdash; buy-and-hold ({_bm_head})"
            benchmark_detail = f"""
            <h2 id="sec-benchmark-detail" class="pbreak">{bm_detail_title}</h2>
            {bm_figure}
            <table class="wide"><thead><tr>
              <th>Ticker</th><th class="num">Buy<span class="subd">{buy_d}</span></th>
              <th class="num">Invested</th><th class="num">Units</th>
              <th class="num">Sell<span class="subd">{sell_d}</span></th>
              <th class="num">Value</th></tr></thead>
              <tbody>
              <tr><td>{bm_ticker}</td><td class="num">{p_in:,.2f}</td>
              <td class="num">{balance:,.2f}</td><td class="num">{units:,.2f}</td>
              <td class="num">{p_out:,.2f}</td><td class="num">{value:,.2f}</td></tr>
              <tr class="tot"><td colspan="5" class="num">CAGR</td><td class="num">{cagr_cell}</td></tr>
              </tbody></table>"""

    # ---- appendix: config + quotes ----
    def two_col(items, k_hdr, v_hdr):
        half = (len(items) + 1) // 2
        def body(chunk):
            return "".join(f"<tr><td class='k'>{k}</td><td>{v}</td></tr>" for k, v in chunk)
        return (f"<table class='appendix'><thead><tr><th>{k_hdr}</th><th>{v_hdr}</th></tr></thead>"
                f"<tbody>{body(items[:half])}</tbody></table>"
                f"<table class='appendix'><thead><tr><th>{k_hdr}</th><th>{v_hdr}</th></tr></thead>"
                f"<tbody>{body(items[half:])}</tbody></table>")

    conf_items = [(k, fmt_conf_value(v)) for k, v in conf.items()]
    conf_html = two_col(conf_items, "Key", "Value")
    quotes_html = two_col(list(quotes.items()), "Ticker", "Description")

    # ---- appendix: account performance (detailed) - the daily equity curve
    # (with the longest-drawdown callout drawn on the chart) and the
    # monthly-return distribution (with its min/max/mean drawn on the chart) ----
    # both figures share this page, so their widths are set to the largest pair
    # that still renders on a single A4 page (88%/76% leaves ~22pt of slack; the
    # equity figure's 4 panels make it too tall for the front page's 92%)
    account_detail_title = "Appendix &mdash; account performance (detailed)"
    account_detail_section = ""
    if img_equity_detail:
        monthly_dist_fig = (f'<figure class="equityfig" style="margin-top:20px">'
                            f'<img src="{img_monthly_dist}" alt="Distribution of monthly returns" '
                            f'style="width:76%">'
                            f'<figcaption>Distribution of monthly returns in dollars, with the mean '
                            f'(dashed).</figcaption></figure>' if img_monthly_dist else "")
        account_detail_section = f"""
        <h2 id="sec-account-detail" class="pbreak">{account_detail_title}</h2>
        <figure class="equityfig"><img src="{img_equity_detail}" alt="Daily equity curve with drawdown, trailing 1-year return and monthly return" style="width:88%">
        <figcaption>Daily equity curve against the buy-and-hold benchmark (top), the drawdown
        from the running equity peak in percent, the trailing one-year return in dollars and
        the monthly return in dollars (bottom).</figcaption></figure>
        {monthly_dist_fig}"""

    # ---- table of contents ----
    # only worth a page of its own in the full report - the short one has few
    # enough sections to navigate without it.
    # (anchor id, title) in body order, skipping the sections that are switched
    # off for this run. Page numbers are filled in by WeasyPrint at render time
    # via target-counter(), so they stay correct however the content paginates.
    # the executive summary and the strategy-vs-benchmark section together make
    # up the front page, directly above this table, so neither is listed
    toc_entries = [("sec-account", "Account performance"),
                    ("sec-trades", "Trade statistics"),
                    ("sec-distribution", "Trade distribution")]
    if mc_section:
        toc_entries.append(("sec-montecarlo", "Monte Carlo simulation"))
    if benchmark_detail:
        toc_entries.append(("sec-benchmark-detail", bm_detail_title))
    toc_entries += [("sec-quotes", "Appendix &mdash; quotes list"),
                    ("sec-config", "Appendix &mdash; configuration")]
    if account_detail_section:
        toc_entries.append(("sec-account-detail", account_detail_title))
    if mfe_mae_section:
        toc_entries.append(("sec-mfemae", mfe_mae_title))
    if full:
        toc_entries.append(("sec-tickers", "Appendix &mdash; ticker plots"))

    toc_html = ("<table class='toc'><tbody>" + "".join(
        f"<tr><td><a href='#{anchor}'>{title}</a></td>"
        f"<td class='pg'><a class='pg' href='#{anchor}'></a></td></tr>"
        for anchor, title in toc_entries) + "</tbody></table>") if full else ''

    # in a short report the trade statistics follow the account performance table
    # on the same page - there is room for both, and with the equity curve moved
    # up to the front page a forced break would leave page 2 nearly empty
    trades_pbreak = ' class="pbreak"' if full else ''

    # ---- assemble ----
    css = f"""
    @page {{
        size: A4 portrait; margin: 16mm 14mm 18mm 14mm;
        font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
        @bottom-left {{ content: "TradeSysX (v{__version__}) \\2022  system summary";
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 8px; color: {TEXT2}; }}
        @bottom-center {{ content: "Page " counter(page) " of " counter(pages);
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 8px; color: {TEXT2}; }}
        @bottom-right {{ content: "{gen_ts}";
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 8px; color: {TEXT2}; }}
    }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: {TEXT};
        font-size: 12px; line-height: 1.55; margin: 0; }}
    h1 {{ font-size: 23px; font-weight: 600; margin: 0 0 3px; letter-spacing: -0.01em; }}
    .headrow {{ margin: 0 0 2px; }}
    .headrow .logo {{ width: 46px; height: 46px; vertical-align: middle; margin-right: 14px; }}
    .headtext {{ display: inline-block; vertical-align: middle; }}
    .headtext h1 {{ margin: 0 0 2px; white-space: nowrap; }}
    .headtext .sub {{ margin: 0; }}
    h2 {{ font-size: 14px; font-weight: 600; margin: 26px 0 11px; padding-bottom: 6px;
        border-bottom: 1px solid {GRID}; letter-spacing: 0.02em; }}
    h3 {{ font-size: 12px; font-weight: 600; color: {TEXT}; margin: 14px 0 4px;
        letter-spacing: 0.02em; }}
    p {{ margin: 0 0 8px; }}
    .sub {{ color: {TEXT2}; font-size: 12.5px; }}
    .brandrule {{ height: 3px; width: 52px; background: {ACCENT}; border-radius: 2px; margin: 12px 0; }}
    .meta {{ color: {TEXT2}; font-size: 11.5px; }}
    .meta b {{ color: {TEXT}; font-weight: 600; }}
    .meta span {{ margin-right: 20px; }}
    .disclaimer {{ color: {TEXT2}; font-size: 9.5px; line-height: 1.5; background: #FAFAF8;
        border: 1px solid {GRID}; border-left: 3px solid {ACCENT}; border-radius: 4px;
        padding: 8px 11px; margin: 12px 0 4px; }}

    .kpis {{ margin: 4px 0 10px; }}
    .kpi {{ display: inline-block; width: 32%; vertical-align: top; border: 1px solid {GRID};
        border-radius: 4px; padding: 11px 13px; margin: 0 0.4% 8px 0; }}
    .kpi .lbl {{ font-size: 9.5px; letter-spacing: 0.06em; text-transform: uppercase;
        color: {TEXT2}; margin: 0; }}
    .kpi .val {{ font-size: 24px; font-weight: 600; margin: 4px 0 1px; letter-spacing: -0.02em; }}
    .kpi .ctx {{ font-size: 10.5px; margin: 0; color: {TEXT2}; }}
    .kpi .ctx.up {{ color: {POS}; }}
    .kpi .ctx.down {{ color: {NEG}; }}
    .badge {{ display: inline-block; font-size: 9px; padding: 1px 6px; border-radius: 20px;
        background: #ECEAF7; color: {ACCENT}; font-weight: 600; margin-left: 6px; vertical-align: 2px; }}

    .cmp {{ margin: 2px 0 4px; }}
    .cmprow {{ margin-bottom: 10px; }}
    .cmprow .name {{ display: inline-block; width: 20%; vertical-align: middle; font-size: 12px; }}
    .cmprow .name small {{ display: block; color: {TEXT2}; font-size: 10px; }}
    .cmprow .track {{ display: inline-block; width: 50%; vertical-align: middle; }}
    .cmprow .cagr {{ display: inline-block; width: 13%; vertical-align: middle; text-align: right;
        font-size: 12px; }}
    .cmprow .cagr .mut {{ color: {TEXT2}; font-size: 9.5px; }}
    .cmprow .maxdd {{ display: inline-block; width: 13%; vertical-align: middle; text-align: right;
        font-size: 12px; color: {NEG}; }}
    .cmprow .maxdd .mut {{ color: {TEXT2}; font-size: 9.5px; }}
    .bar {{ height: 28px; border-radius: 3px; color: #fff; font-size: 12px; font-weight: 600;
        line-height: 28px; text-align: right; padding-right: 9px; min-width: 64px; }}
    .bar.s {{ background: {ACCENT}; }}
    .bar.b {{ background: {NEUTRAL}; color: #3a3934; }}

    figure {{ margin: 6px 0; }}
    figure img {{ width: 100%; }}
    figcaption, .cap {{ font-size: 10.5px; color: {TEXT2}; margin-top: 3px; }}
    /* keep a block together on one page (no internal page break) */
    .keep {{ break-inside: avoid; }}
    /* the MFE/MAE scatters, sized so both fit one page together */
    .mfemae figure {{ margin: 2px 0 30px; }}
    .mfemae figure img {{ width: 92%; display: block; margin: 0 auto; }}
    /* the equity curve shares the front page with the summary and benchmark
       sections - at 92% it fits with ~14pt to spare, where full width overruns
       the page by a few points and pushes the whole figure to page 2 */
    .equityfig {{ page-break-inside: avoid; }}
    .equityfig img {{ width: 92%; display: block; margin: 0 auto; }}
    .nosplit {{ page-break-inside: avoid; }}

    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    .statgrid table {{ display: inline-table; width: 48.5%; margin-right: 2%; vertical-align: top; }}
    .statgrid table:last-child {{ margin-right: 0; }}
    th {{ text-align: left; color: {TEXT2}; font-weight: 600; font-size: 10px;
        letter-spacing: 0.04em; text-transform: uppercase; padding: 6px 8px;
        border-bottom: 1.5px solid {GRID}; vertical-align: top; }}
    td {{ padding: 5px 8px; border-bottom: 1px solid {GRID}; }}
    td.num, th.num {{ text-align: right; }}
    td.k {{ color: {TEXT2}; }}
    .pos {{ color: {POS}; font-weight: 600; }}
    .neg {{ color: {NEG}; font-weight: 600; }}
    .warn {{ color: {IND_GOLD}; font-weight: 600; }}
    td.tag {{ color: {TEXT2}; font-size: 10.5px; }}
    tr.tot td {{ font-weight: 600; border-top: 1.5px solid {GRID}; }}
    th .subd {{ display: block; font-weight: 400; text-transform: none;
        letter-spacing: 0; font-size: 9px; color: {TEXT2}; }}
    table.wide {{ margin-top: 14px; }}
    table.appendix {{ display: inline-table; width: 49%; vertical-align: top; }}
    table.appendix:first-of-type {{ margin-right: 1.5%; }}

    /* table of contents - page numbers are resolved by WeasyPrint from the
       link target, so they follow the real pagination. The row padding is tuned
       so that all 10 entries (every optional section switched on) still fit on
       the front page below the summary and benchmark blocks - at 6px the last
       row is orphaned onto page 2 */
    table.toc {{ margin: 2px 0 4px; }}
    table.toc td {{ padding: 4px 0; border-bottom: 1px dotted {GRID}; }}
    table.toc td.pg {{ width: 3em; text-align: right; color: {TEXT2}; }}
    table.toc a {{ color: {TEXT}; text-decoration: none; }}
    table.toc a.pg {{ color: {TEXT2}; }}
    table.toc a.pg::after {{ content: target-counter(attr(href), page); }}

    .pbreak {{ page-break-before: always; }}
    """

    logo_uri = _logo_data_uri()
    logo_img = f'<img class="logo" src="{logo_uri}" alt="TradeSysX logo">' if logo_uri else ""

    body = f"""
    <div class="headrow">
      {logo_img}
      <div class="headtext">
        <h1>TradeSysX system summary</h1>
        <p class="sub">{strategy_desc}</p>
      </div>
    </div>
    <div class="brandrule"></div>
    <p class="meta">
      <span><b>Period</b> {date_range}</span>
      <span><b>Universe</b> {len(quotes)} tickers</span>
      <span><b>Benchmark</b> {bm_desc if benchmark_enabled else '&ndash;'}</span>
      <span><b>Generated</b> {gen_ts}</span>
    </p>

    <p class="disclaimer">This report is generated for system evaluation and research purposes only.
    It presents backtested results with simulated execution and does not constitute financial advice
    or a recommendation to buy, sell or hold any security, or to pursue any course of action.
    Past performance does not guarantee future results.</p>

    <h2>Executive summary</h2>
    <div class="kpis">{kpi_html}</div>

    {f'<h2 id="sec-benchmark">Strategy vs benchmark</h2>{benchmark_bars}' if benchmark_bars else ''}

    {f'<h2>Contents</h2>{toc_html}' if toc_html else ''}

    <h2 id="sec-account">Account performance</h2>
    <figure class="equityfig"><img src="{img_equity}" alt="Account value over time">
    <figcaption>Simulated account value (equity curve) against the buy-and-hold benchmark (dashed).</figcaption></figure>
    <div class="statgrid nosplit" style="margin-top:1.2em">
      <table><tbody>{sim_rows_left}</tbody></table>
      <table><tbody>{sim_rows_right}</tbody></table>
    </div>

    <h2 id="sec-trades"{trades_pbreak}>Trade statistics</h2>
    <div class="statgrid">
      <table><tbody>{stats_left}</tbody></table>
      <table><tbody>{stats_right}</tbody></table>
    </div>
    {trades_table_html}

    <h2 id="sec-distribution">Trade distribution</h2>
    <figure><img src="{img_bars}" alt="R-multiple of each trade in sequence">
    <figcaption>R-multiple of each trade in sequence (wins green, losses red) with the
    30-trade rolling average.</figcaption></figure>
    <figure><img src="{img_dist}" alt="Histogram of trade R-multiples">
    <figcaption>Distribution of trade outcomes in R-multiples.</figcaption></figure>

    {mc_section}

    {benchmark_detail}

    <h2 id="sec-quotes" class="pbreak">Appendix &mdash; quotes list</h2>
    {quotes_html}
    <h2 id="sec-config">Appendix &mdash; configuration</h2>
    {conf_html}
    {account_detail_section}
    {mfe_mae_section}
    """

    if full:
        rows = "".join(
            f'<img src="{_data_uri(ctx.outpath("plots", f"{ticker}_plot.png"))}" style="width:100%">'
            for ticker in quotes
        )
        body += f'<h2 id="sec-tickers" class="pbreak">Appendix &mdash; ticker plots</h2>{rows}'

    html_content = f"<html><head><meta charset=\"utf-8\"><style>{css}</style></head><body>{body}</body></html>"

    # same filename for short and full (full just appends the ticker plots) -
    # a separate *_full.pdf name was confusing
    pdf_path = ctx.outpath("system_summary.pdf")
    HTML(string=html_content).write_pdf(pdf_path)

    logger.info(f"Report saved: {pdf_path}")


def format_to_2_decimals(x):
    # Matches numbers, including negatives and decimals
    if re.match(r"^-?\d+(\.\d+)?$", str(x)):
        return f"{float(x):.2f}"
    return x

def compute_position_size(conf, balance, total_equity, stats):
    '''return the amount of capital to allocate per trade.'''

    ps = conf["pos_sizing"]

    if ps == "core_equity_risk":
        return balance * conf["risk_percent"] # risk expressed as a % of cash balance
    elif ps == "total_equity_risk":
        return total_equity * conf["risk_percent"] # risk expressed as a % of total equity
    elif ps == "fixed_dollar_risk":
        return conf["risk_amount"]            # total risk per trade in dollars
    elif ps == "fixed_ratio":
        return balance / conf["pos_ratio"]    # position size as ratio of balance
    elif ps == "fixed_amount":
        return conf["pos_amount"]             # position size as a fixed_amount
    elif ps == "kelly":
        return conf['kelly_ratio'] * stats.kelly_crit * balance # position size as per the kelly criterion
    else:
        logger.critical(f"The position sizing strategy [{conf['pos_sizing']}] does not exist!")
        sys.exit(1)

def risk_basis(conf, balance, total_equity):
    ''' returns the capital base the position size was computed against, so the
    risk percentage per trade is expressed relative to the same capital that
    compute_position_size used (total equity for total_equity_risk, the cash
    balance for every other sizing method). '''
    return total_equity if conf["pos_sizing"] == "total_equity_risk" else balance

def do_balance_simulation(dframe, df_trades_table, conf, last_close_date, ctx, stats):
    ''' simulates the virtual account balance for the trades list '''

    dframe.sort_values(by='Date', ascending=True, inplace=True)
    dframe.reset_index(drop=True, inplace=True)

    # ensure the 'Date' column is in datetime format
    dframe['Date'] = pd.to_datetime(dframe['Date'], errors='coerce')
    dframe['Date'] = dframe['Date'].dt.strftime('%Y-%m-%d')
    
    # Containers for results
    units_lst: List[float] = []
    units_full_lst: List[float] = []  # unrounded units, for the equity curve replay
    gain_lst: List[float] = []
    abs_risk_lst: List[float] = []
    risk_lst: List[float] = []
    invest_lst: List[float] = []
    balance_lst: List[float] = []
    total_balance_lst: List[float] = []
    active_trades: Dict[str, float] = {}  # ticker -> units held

    balance = total_balance = float(conf['balance'])
    logger.info(f"Starting balance  : {balance:,.2f}")
    logger.info(f"Position sizing   : {rp.pos_sizing_label(conf)}")

    ohlc_cache = load_ohlc_cache(dframe['Ticker'].unique(), ctx)

    for row in dframe.itertuples(index=False):

        if row.Enter != '-':
            units, cap_invested = _get_capital_invested(row, conf, balance, total_balance, stats)
            active_trades[row.Ticker] = units
            gain_lst.append('-')
            if units == 0:
                # trade not taken (below min_invest or balance too low) - blank the
                # units/risk so this dead row is excluded from the risk averages
                units_lst.append('-')
                units_full_lst.append('-')
                abs_risk_lst.append('-')
                risk_lst.append('-')
            else:
                units_lst.append(round(units, 2))
                units_full_lst.append(units)
                risk_base = risk_basis(conf, balance, total_balance)
                abs_risk = units * row.Risk if risk_base else 0
                risk_pct = (abs_risk / risk_base) * 100 if risk_base else 0
                abs_risk_lst.append(round(abs_risk, 2))
                risk_lst.append(round(risk_pct, 2))

        if row.Exit != '-':
            units = active_trades[row.Ticker]
            tot_profit = units * round(row.Profit, 2)
            exit_fee = (units * row.Exit) * float(conf['trading_fee']) / 100
            cap_invested = -(units * row.Exit - exit_fee)
            #logger.debug(f"Trading fee (exit ): {exit_fee:.2f} ({row.Ticker})")
            active_trades[row.Ticker] = 0
            # units == 0 means the paired entry was never taken - blank its gain too
            gain_lst.append(round(tot_profit, 2) if units != 0 else '-')
            units_lst.append('-')
            units_full_lst.append('-')
            abs_risk_lst.append('-')
            risk_lst.append('-')

        total_invested_value = get_total_invested_value(active_trades, row.Date, ohlc_cache)
        balance -= cap_invested
        total_balance = total_invested_value + balance

        invest_lst.append(round(cap_invested, 2))
        balance_lst.append(round(balance, 2))
        total_balance_lst.append(round(total_balance, 2))

    dframe.loc[:,"Units"] = units_lst
    dframe.loc[:,"Gain"] = gain_lst
    dframe.loc[:,"RiskAbs"] = abs_risk_lst
    dframe.loc[:,"RiskPerc"] = risk_lst
    dframe.loc[:,"Invested"] = invest_lst
    dframe.loc[:,"Balance"] = balance_lst
    dframe.loc[:,"Value"] = total_balance_lst

    # snapshot the raw trade events for the daily equity curve, before the open
    # trades are closed out below and the columns are reformatted for display.
    # Units uses the unrounded units_full_lst (not the display-rounded 'Units'
    # column) so the equity curve's final mark-to-market lines up with the
    # balance simulation's own full-precision close-out below.
    equity_events = dframe[['Date', 'Ticker', 'Enter', 'Exit', 'Invested']].copy()
    equity_events['Units'] = units_full_lst

    # average balance and investment before open trade closure
    avg_balance = dframe["Balance"].mean()
    avg_value = dframe["Value"].mean()

    invested_lst = dframe["Invested"].tolist()
    pos_inv_lst = [x for x in invested_lst if x > 0]
    pos_inv_cnt = len(pos_inv_lst)
    avg_invested = sum(pos_inv_lst)/pos_inv_cnt

    # close all open trades to get the total balance
    closed_open_trades = 0
    for key, value in active_trades.items():
        if value != 0:
            tmp_df = df_trades_table.loc[(df_trades_table['Ticker'] == key) & (df_trades_table['LastClose'] != '-'), :]
            closed_ret = float(tmp_df['LastClose'].iloc[0]) * float(value)
            balance += closed_ret
            closed_open_trades += 1
            logger.debug("Closed: {} ({:,.2f})".format(key, closed_ret))
            tmp_row = {
                'Date': last_close_date.strftime('%Y-%m-%d'),
                'Ticker': f"({key})",
                'Enter': tmp_df['PriceIn'].iloc[0],
                'Risk': tmp_df['Risk'].iloc[0],
                'Profit': tmp_df['Profit'].iloc[0],
                'Units': round(float(value), 2),
                'Gain': round(float(tmp_df['Profit'].iloc[0]) * float(value), 2),
                'Exit': float(tmp_df['LastClose'].iloc[0]),
                'Invested': -round(float(closed_ret), 2),
                'Balance': round(float(balance), 2),
                'Value': "-",
                'RiskAbs': "-",
                'RiskPerc': "-"
            }
            dframe = pd.concat([dframe, pd.DataFrame([tmp_row])], ignore_index=True)

    dframe['Enter'] = dframe['Enter'].apply(format_to_2_decimals)
    dframe['Exit'] = dframe['Exit'].apply(format_to_2_decimals)
    dframe['Profit'] = dframe['Profit'].apply(format_to_2_decimals)

    # absolute and % wise risk
    abs_risk_df = dframe[['RiskAbs']].copy()
    per_risk_df = dframe[['RiskPerc']].copy()
    abs_risk_df['RiskAbs'] = pd.to_numeric(abs_risk_df['RiskAbs'], errors='coerce')
    per_risk_df['RiskPerc'] = pd.to_numeric(per_risk_df['RiskPerc'], errors='coerce')
    avg_risk_abs = abs_risk_df['RiskAbs'].mean()
    avg_risk_per = per_risk_df['RiskPerc'].mean()

    # store values for use by later pipeline steps
    stats.avg_risk = avg_risk_abs

    cagr = ann_return(conf['balance'], balance, stats.trades_len / 365) if stats.trades_len else 0.0

    # store balance-simulation results for the summary report's balance table
    stats.open_trades_closed = closed_open_trades
    stats.avg_invested = avg_invested
    stats.avg_balance = avg_balance
    stats.avg_value = avg_value
    stats.avg_risk_per = avg_risk_per
    stats.final_balance = balance
    stats.cagr = cagr

    logger.info(f"Open trades closed: {closed_open_trades}")
    logger.info(f"Average investment: {avg_invested:,.2f}")
    logger.info(f"Average value     : {avg_value:,.2f}")
    logger.info(f"Average balance   : {avg_balance:,.2f}")
    logger.info(f"Average risk ($)  : {avg_risk_abs:,.2f}")
    logger.info(f"Average risk (%)  : {avg_risk_per:.2f}")

    # sanity check the sum of the invested colum (start balance + -(invested) = final balance)
    total_invested = dframe['Invested'].sum()
    logger.info(f"Total invested    : {total_invested:,.2f}")
    logger.info(f"Final balance     : {balance:,.2f}")
    logger.info(f"CAGR              : {cagr:.1%}")

    logger.debug("\n%s", dframe)
    dframe.to_csv(ctx.outpath("tables/", "trades_list.csv"), index=False)

    # save to pdf file
    dframe.index = dframe.index + 1
    dframe['Date'] = pd.to_datetime(dframe['Date'], errors='coerce').dt.strftime('%d-%m-%Y')
    html = df_to_html(dframe)
    HTML(string=html).write_pdf(ctx.outpath("trades_list.pdf"))

    # daily equity curve over the whole backtest period, derived from the same events
    do_equity_simulation(equity_events, conf, ctx, stats, df_trades_table)

    return dframe

def _trading_calendar(conf, ctx, ohlc_cache):
    ''' the master trading calendar for the equity curve: the benchmark ticker
        spans the whole configured range (also while no position was open), the
        traded tickers fill in any session it happens to miss. '''

    dates = pd.DatetimeIndex([])

    bm_ticker = conf.get('bm_ticker', 'URTH')
    if bm_ticker != 'quote-lst':
        try:
            bm_df = pd.read_csv(ctx.outpath('data', f"{bm_ticker}_ohlc_raw.csv"))
            dates = dates.union(pd.to_datetime(bm_df['Date'], errors='coerce').dropna())
        except Exception as e:
            logger.warning(f"No benchmark data for the equity calendar: {e}")

    for df in ohlc_cache.values():
        if df is None:
            continue
        dates = dates.union(pd.to_datetime(df.index, errors='coerce').dropna())

    return dates.sort_values()

def _daily_close_frame(ohlc_cache, calendar):
    ''' per-ticker daily close prices reindexed onto the master calendar, so a
        position can be marked to market on every trading day. '''

    close = pd.DataFrame(index=calendar)
    for ticker, df in ohlc_cache.items():
        if df is None or 'Close' not in df.columns:
            continue
        prices = pd.to_numeric(df['Close'], errors='coerce')
        prices.index = pd.to_datetime(df.index, errors='coerce')
        prices = prices[~prices.index.duplicated(keep='last')].sort_index()
        close[ticker] = prices.reindex(calendar, method='ffill')
    return close

def do_equity_simulation(events_df, conf, ctx, stats, df_trades_table=None):
    ''' build the daily equity curve over the full backtest period and derive
        the time-based performance statistics from it.

        The trades list holds one row per trade event, which makes calendar-based
        statistics impossible to compute from it. This table instead has one row
        per trading day - from the first session to the last close - holding the
        cash balance, the marked-to-market value of the open positions (at that
        day's close) and their sum, the total equity. '''

    ohlc_cache = load_ohlc_cache(events_df['Ticker'].unique(), ctx)
    calendar = _trading_calendar(conf, ctx, ohlc_cache)
    if len(calendar) == 0:
        logger.warning("No trading calendar available - skipping the equity curve")
        return None

    close = _daily_close_frame(ohlc_cache, calendar)

    # replay the trade events onto the calendar: units held per ticker (carried
    # forward between events) and the cash movement on the day of each event
    units = pd.DataFrame(np.nan, index=calendar, columns=close.columns)
    units.iloc[0] = 0.0
    cash_delta = pd.Series(0.0, index=calendar)

    held = {ticker: 0.0 for ticker in close.columns}
    for row in events_df.itertuples(index=False):
        if row.Ticker not in held:
            continue
        date = pd.to_datetime(row.Date, errors='coerce')
        if pd.isna(date):
            continue
        # snap onto the calendar (an event can only be acted on from that session on)
        pos = calendar.searchsorted(date)
        if pos >= len(calendar):
            continue
        date = calendar[pos]

        if row.Exit != '-':
            held[row.Ticker] = 0.0
        elif row.Enter != '-' and row.Units != '-':
            held[row.Ticker] = float(row.Units)

        units.at[date, row.Ticker] = held[row.Ticker]
        cash_delta.at[date] += -float(row.Invested)

    units = units.ffill().fillna(0.0)

    # mark still-open positions on the final day at their own LastClose (the
    # same price do_balance_simulation's close-out uses), rather than that
    # day's raw OHLC close, so the equity curve's final value agrees with the
    # balance simulation's reported final balance
    if df_trades_table is not None:
        last_date = calendar[-1]
        for ticker in close.columns:
            if units.at[last_date, ticker] == 0:
                continue
            tmp = df_trades_table.loc[
                (df_trades_table['Ticker'] == ticker) & (df_trades_table['LastClose'] != '-'),
                'LastClose']
            if not tmp.empty:
                close.at[last_date, ticker] = float(tmp.iloc[0])

    holdings = (units * close).sum(axis=1)
    cash = float(conf['balance']) + cash_delta.cumsum()
    equity = cash + holdings

    # running peak and the drawdown relative to it
    peak = equity.cummax()
    drawdown = (equity / peak - 1.0) * 100

    # trailing one-year return in $: today's equity minus the equity one calendar
    # year back (the last session on or before that date)
    year_ago = equity.reindex(calendar - pd.DateOffset(years=1), method='ffill')
    trailing_1y = equity.to_numpy() - year_ago.to_numpy()
    trailing_1y = pd.Series(trailing_1y, index=calendar)

    # monthly return in $, booked on the last trading day of each month
    month_end = ~calendar.to_period('M').duplicated(keep='last')
    month_close = equity[month_end]
    month_ret = month_close.diff()
    if len(month_ret):
        month_ret.iloc[0] = month_close.iloc[0] - float(conf['balance'])

    # monthly return in %, mirroring the series above but normalized by the
    # equity level at the start of each month - needed for the Sharpe ratio,
    # since the dollar-based series alone would be skewed by account growth
    month_ret_pct = (month_close / month_close.shift() - 1.0) * 100
    if len(month_ret_pct):
        month_ret_pct.iloc[0] = (month_close.iloc[0] / float(conf['balance']) - 1.0) * 100

    # longest stretch between two equity highs (drawdown recovery length). A day
    # at or above the previous running peak counts as a high, so flat periods
    # without an open position don't extend a recovery.
    at_high = equity.ge(peak.shift().fillna(equity.iloc[0]))
    high_dates = calendar[at_high]
    max_recovery, rec_from, rec_to = 0, None, None
    if len(high_dates) > 1:
        gaps = (high_dates[1:] - high_dates[:-1]).days
        idx = int(np.argmax(gaps))
        max_recovery = int(gaps[idx])
        rec_from, rec_to = high_dates[idx], high_dates[idx + 1]
    ongoing = int((calendar[-1] - high_dates[-1]).days) if len(high_dates) else 0

    dframe = pd.DataFrame({
        'Date': calendar.strftime('%Y-%m-%d'),
        'Cash': cash.round(2).to_numpy(),
        'Holdings': holdings.round(2).to_numpy(),
        'Equity': equity.round(2).to_numpy(),
        'Peak': peak.round(2).to_numpy(),
        'DDPerc': drawdown.round(2).to_numpy(),
        'Trail1Y': trailing_1y.round(2).to_numpy(),
        'MonthRet': month_ret.round(2).reindex(calendar).to_numpy(),
        'MonthRetPct': month_ret_pct.round(2).reindex(calendar).to_numpy(),
    })
    dframe = dframe.fillna('-')

    # store values for use by later pipeline steps
    stats.best_month = month_ret.max() if len(month_ret) else 0.0
    stats.worst_month = month_ret.min() if len(month_ret) else 0.0
    stats.avg_month = month_ret.mean() if len(month_ret) else 0.0
    stats.std_month = month_ret.std() if len(month_ret) else 0.0
    stats.avg_month_pct = month_ret_pct.mean() if len(month_ret_pct) else 0.0
    stats.std_month_pct = month_ret_pct.std() if len(month_ret_pct) else 0.0
    stats.best_trailing_1y = trailing_1y.max()
    stats.worst_trailing_1y = trailing_1y.min()
    stats.avg_trailing_1y = trailing_1y.mean()
    stats.max_dd_recovery = max_recovery
    stats.max_dd_recovery_from = rec_from.strftime('%Y-%m-%d') if rec_from is not None else "-"
    stats.max_dd_recovery_to = rec_to.strftime('%Y-%m-%d') if rec_to is not None else "-"

    # real max drawdown (%) of the daily equity curve - peak-to-trough, the
    # basis for the MAR ratio (kept separate from the Monte Carlo simulated
    # stats.max_drawdown and the trade-event-based strat_dd used elsewhere)
    stats.max_drawdown_pct = float(-drawdown.min()) if len(drawdown) else 0.0

    # Sharpe ratio: mean / stdev of monthly % returns, annualized (0% risk-free
    # rate assumed). Undefined (None) with fewer than two months of data or a
    # flat return series, rather than raising or showing a misleading 0.00
    stats.sharpe_ratio = (
        (stats.avg_month_pct / stats.std_month_pct) * math.sqrt(12)
        if stats.std_month_pct and not math.isnan(stats.std_month_pct)
        else None
    )

    # MAR ratio: CAGR over the real max drawdown above. Undefined (None) when
    # the equity curve never had a drawdown (max_drawdown_pct == 0)
    stats.mar_ratio = (stats.cagr * 100) / stats.max_drawdown_pct if stats.max_drawdown_pct else None

    #logger.info(f"Equity curve rows : {len(dframe):,} ({calendar[0]:%Y-%m-%d} - {calendar[-1]:%Y-%m-%d})")
    #logger.info(f"Final equity      : {equity.iloc[-1]:,.2f}")
    #logger.info(f"Monthly return ($): {stats.worst_month:,.2f} (min) / {stats.best_month:,.2f} (max) / {stats.avg_month:,.2f} (avg)")
    #logger.info(f"Trailing 1y ($)   : {stats.worst_trailing_1y:,.2f} (min) / {stats.best_trailing_1y:,.2f} (max) / {stats.avg_trailing_1y:,.2f} (avg)")
    logger.info(f"Sharpe ratio      : {stats.sharpe_ratio:.2f}" if stats.sharpe_ratio is not None else "Sharpe ratio      : -")
    logger.info(f"MAR ratio         : {stats.mar_ratio:.2f}" if stats.mar_ratio is not None else "MAR ratio         : -")
    logger.info(f"Monthly return ($): {stats.avg_month:,.2f}")
    logger.info(f"Longest drawdown  : {max_recovery} days ({stats.max_dd_recovery_from} -> {stats.max_dd_recovery_to})")
    if ongoing > max_recovery:
        logger.info(f"Open drawdown     : {ongoing} days, not recovered at the last close")
    logger.debug("\n%s", dframe)
    dframe.to_csv(ctx.outpath('tables', "equity_curve.csv"), index=False)

    equity_plot(dframe, conf, ctx, max_recovery, rec_from, rec_to)
    monthly_dist_plot(dframe, conf, ctx)

    return dframe

def do_monte_carlo_simulation_sampled(total_trades_list, conf, ctx, stats):
    ''' takes the list of R-multiples and randomly samples from the list (bag of marbles simulation)'''

    # extract Rmul values from the trades list
    Rmul_arr = total_trades_list['Rmul'].dropna().to_numpy()

    # set the average risk 
    risk = stats.avg_risk / conf['balance']

    # precompute the buy-and-hold benchmark for the plot, if enabled
    benchmark = None
    if conf.get('benchmark', True):
        val_out = _get_benchmark_result(conf, ctx)
        ann_ret_hodl = ann_return(conf['balance'], val_out, stats.trades_len/365)
        benchmark = (val_out, ann_ret_hodl)

    run_monte_carlo_sampled(Rmul_arr, conf, ctx, stats, risk,
                            output_filename="monte_carlo_plot.png",
                            benchmark=benchmark)

def run_monte_carlo_sampled(Rmul_arr, conf, ctx, stats, risk, output_filename="monte_carlo_plot.png", benchmark=None):
    ''' run a Monte Carlo balance simulation by sampling from the given R-multiple distribution (bag of marbles) '''

    logger.info(f"Number of samples      : {conf['iterations']}")

    logger.info(f"Trades total           : {len(Rmul_arr)}")
    logger.info(f"Real Rmul average      : {np.mean(Rmul_arr):.2f}")
    logger.info(f"Real Rmul maximum      : {Rmul_arr.max():.2f}")
    logger.info(f"Real Rmul minimum      : {Rmul_arr.min():.2f}")
    logger.info(f"System Quality Number  : {stats.sqn:.2f}")

    # sample from the real distribution as measured by the closed trades
    multiset = Rmul_arr.tolist()
    sample_count = conf['iterations']
    Rmul_sample = np.random.choice(multiset, size=sample_count, replace=True)

    logger.info(f"Sampled Rmul average   : {np.mean(Rmul_sample):.2f} ({conf['iterations']} samples)")
    logger.info(f"Risk per trade (%)     : {risk*100:.2f}")

    sim_runs = conf['iterations']
    # array to hold balance values of all iterations (for visualisation)
    N = sim_runs                                                                       # number of simulations (columns)
    M = len(Rmul_arr) if len(Rmul_arr) <= conf['sim_len_max'] else conf['sim_len_max'] # number of trades (rows)

    start_balance = float(conf['balance'])
    balances = np.empty((M, N))

    max_neg_run = 0
    avg_neg_run = 0.0
    sqn_sum = 0.0
    # SQN of each simulated run of M trades, derived exactly like the real SQN
    # (mean/stdev of the run's R-multiples, capped at 100 trades), so the mean
    # sim SQN is directly comparable to the real one
    sqn_factor = math.sqrt(min(M, 100))

    # Monte Carlo balance simulation
    for it in range(0, N):

        # draw series of samples from the original distribution (of size M)
        Rmul_sampled = np.random.choice(multiset, size=M, replace=True)

        # store longest neg streak
        neg_run = longest_negative_streak(Rmul_sampled)
        avg_neg_run = ((avg_neg_run * it) + neg_run) / (it+1)
        if neg_run > max_neg_run:
            max_neg_run = neg_run

        # SQN of this run (sample stdev, ddof=1, to match the real SQN)
        run_std = Rmul_sampled.std(ddof=1)
        if run_std > 0:
            sqn_sum += (Rmul_sampled.mean() / run_std) * sqn_factor

        # cumulative balance path for this iteration (balance *= 1 + risk*Rmul each trade)
        factors = 1.0 + risk * Rmul_sampled
        balances[:, it] = start_balance * np.cumprod(factors)

    min_balance = min(start_balance, balances.min())

    # worst peak-to-trough decline across all simulated paths: for each path track
    # the running peak (including the starting balance) and the largest drop from it
    full_paths = np.vstack([np.full((1, N), start_balance), balances])  # (M+1, N)
    running_peak = np.maximum.accumulate(full_paths, axis=0)
    max_drawdown = float(((running_peak - full_paths) / running_peak).max()) * 100.0

    mc_result_df = pd.DataFrame(balances, columns=[f'{i}' for i in range(N)])

    # insert first row with the starting balance (same for all simulation runs)
    start_row = [conf['balance']] * N
    start_row_df = pd.DataFrame([start_row], columns=mc_result_df.columns)
    mc_result_df = pd.concat([start_row_df, mc_result_df], ignore_index=True)

    # store values for use by later pipeline steps
    stats.max_drawdown = max_drawdown
    stats.min_balance = min_balance
    # lowest final (ending) balance across all simulated runs, as opposed to
    # min_balance which is the lowest value reached at any point in any run
    stats.min_end_balance = float(balances[-1].min())
    stats.avg_loss_streak = avg_neg_run
    stats.max_loss_streak = max_neg_run
    stats.rmul_avg_sampled = float(np.mean(Rmul_sample))
    stats.sqn_sampled = sqn_sum / N

    last_row = mc_result_df.iloc[-1]
    logger.info("==== simulation results ====")
    logger.info(f"Median                 : {last_row.median():,.0f}")
    logger.info(f"Stdev                  : {last_row.std():,.0f}")
    logger.info(f"Max                    : {last_row.max():,.0f}")
    logger.info(f"Min                    : {last_row.min():,.0f}")
    logger.info(f"Loss streak avg        : {avg_neg_run:.0f}")
    logger.info(f"Loss streak max        : {max_neg_run:.0f}")
    logger.info(f"Minimum balance        : {stats.min_balance:,.0f}")
    logger.info(f"Max drawdown (%)       : {stats.max_drawdown:.1f}")
    logger.info(f"Sampled SQN            : {stats.sqn_sampled:.2f} (real {stats.sqn:.2f})")

    # save the balances and plot the result (see simulation plot)
    plot_monte_carlo_results_sampled(mc_result_df, conf, ctx, stats, risk, np.mean(Rmul_arr), np.mean(Rmul_sample), avg_neg_run, max_neg_run,
                                      output_filename=output_filename, benchmark=benchmark)

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

def _run_streaks(flags):
    ''' longest and average length of consecutive True runs in `flags`.
    Returns (max, avg), where avg is the mean run length over completed
    runs (0 if there are none). '''
    runs = []
    cur_len = 0
    for f in flags:
        if f:
            cur_len += 1
        elif cur_len:
            runs.append(cur_len)
            cur_len = 0
    if cur_len:
        runs.append(cur_len)
    if not runs:
        return 0, 0.0
    return max(runs), sum(runs) / len(runs)

def win_streaks(values):
    ''' longest and average run of consecutive winning trades (R > 0),
    matching the winners/losers split used elsewhere in the stats. '''
    return _run_streaks([v > 0 for v in values])

def loss_streaks(values):
    ''' longest and average run of consecutive losing trades (R <= 0, so
    break-even counts as a loss, matching the winners/losers split). '''
    return _run_streaks([v <= 0 for v in values])

def ann_return(start_capital: float, end_capital: float, years: float) -> float:
    ''' Compute the annualized rate of return (CAGR) '''
    ratio = end_capital / start_capital
    return ratio ** (1.0 / years) - 1.0

def plot_monte_carlo_results_sampled(mc_result_df, conf, ctx, stats, risk, Rmul_avg, Rmul_avg_sampled, avg_neg_run, max_neg_run,
                                      output_filename="monte_carlo_plot.png", benchmark=None):
    ''' plot the results of the monte carlo simulation '''

    if conf.get('report_style', 'styled') == 'styled':
        rp.styled_montecarlo_plot(mc_result_df, conf, ctx, stats, risk, benchmark,
                                  output_filename=output_filename)
        return

    # only plot a fraction of the simulated iterations (all iterations still count towards the stats below)
    plot_fraction = conf.get('plot_frac', 0.1)
    n_plot = max(1, int(round(mc_result_df.shape[1] * plot_fraction)))
    plot_cols = np.random.choice(mc_result_df.columns, size=n_plot, replace=False)
    plot_df = mc_result_df[plot_cols]

    # plot the sampled subset of balance series
    sns.set_style("white")
    ax = plot_df.plot(
        figsize=(10, 5),
        color='gray',
        linewidth=0.1,
        marker=None,
        legend=False
    )

    # show a marker for the final balance only
    x_last = mc_result_df.index[-1]
    for _, series in plot_df.items():
        y_last = series.iloc[-1]
        ax.scatter(
            x_last, y_last,
            marker='o',
            s=4**2,
            color='brown',
            alpha=0.2
        )

    # Y-axis limit = "outlier-cutoff" * standard deviation of trades distribution,
    # expanded to fit the HODL benchmark if it lies above the simulation results
    y_max = mc_result_df.iloc[-1].median() + (conf['outlier'] * mc_result_df.iloc[-1].std())
    if benchmark is not None:
        val_out, _ = benchmark
        y_max = max(y_max, val_out * 1.05)
    plt.ylim(bottom=0, top=y_max)

    # plot min-max values as text box
    sim_str = (
        f"Trades      : {x_last}\n"
        f"Min         : ${mc_result_df.iloc[-1].min():,.0f}\n"
        f"Max         : ${mc_result_df.iloc[-1].max():,.0f}\n"
        f"Std         : ${mc_result_df.iloc[-1].std():,.0f}\n"
        f"Risk        : {risk*100:,.2f}%\n"
        f"Loss avg    : {avg_neg_run:.0f}x\n"
        f"Loss max    : {max_neg_run:.0f}x\n"
        f"Max drawdown: {stats.max_drawdown:.1f}%\n"
        f"Min balance : ${stats.min_balance:,.0f}\n"
        f"Ravg (sim)  : {Rmul_avg_sampled:.2f}\n"
        f"Ravg (real) : {Rmul_avg:.2f}\n"
        f"SQN         : {stats.sqn:.2f}"
    )
    # Pick the corner with the fewest simulation paths passing through it.
    # Each candidate defines a region (row slice × y-fraction band); we count
    # how many (row, sim) data points fall inside and choose the emptiest corner.
    if y_max > 0:
        _n  = len(plot_df)
        _q  = max(1, int(_n * 0.25))
        _d  = plot_df.values
        _candidates = [
            # (box_x, box_y, ha, va, row_slice, y_lo_frac, y_hi_frac)
            (0.03, 0.97, 'left',  'top',    slice(0, _q),        0.70, 1.00),  # upper-left
            (0.97, 0.97, 'right', 'top',    slice(_n - _q, _n),  0.70, 1.00),  # upper-right
            (0.03, 0.03, 'left',  'bottom', slice(0, _q),        0.00, 0.30),  # lower-left
            # lower-right is reserved for the "samples plotted" textbox
        ]
        box_x, box_y, box_ha, box_va, *_ = min(
            _candidates,
            key=lambda c: np.sum((_d[c[4]] >= c[5] * y_max) & (_d[c[4]] <= c[6] * y_max))
        )
    else:
        box_x, box_y, box_ha, box_va = 0.03, 0.97, 'left', 'top'
    ax.text(
        box_x, box_y, sim_str,
        transform=plt.gca().transAxes,
        fontsize=8,
        fontfamily='Monospace',
        verticalalignment=box_va,
        horizontalalignment=box_ha,
        bbox=dict(
            facecolor='white',
            alpha=1.0,
            boxstyle='round,pad=0.5',
            edgecolor='gray'
        )
    )

    # lower-right textbox: percentage of simulation runs actually drawn on the plot
    ax.text(
        0.99, 0.01, f"{n_plot/mc_result_df.shape[1]:.0%} of samples plotted",
        transform=plt.gca().transAxes,
        fontsize=8,
        fontfamily='Monospace',
        verticalalignment='bottom',
        horizontalalignment='right',
        bbox=dict(
            facecolor='white',
            alpha=0.0,
            edgecolor='none'
        )
    )

    x_first = mc_result_df.index[0]

    ax.set_title(f"Monte Carlo simulation [{conf['iterations']}x]", fontsize=16, pad=25)
    ax.plot([x_first, x_last], [conf['balance'], conf['balance']], color='green', linestyle='--', linewidth=1, alpha=.7)
    ax.plot([x_first, x_last], [mc_result_df.iloc[-1].median(), mc_result_df.iloc[-1].median()], color='brown', linestyle='dotted', linewidth=1.5, alpha=.7, label='Median')

    # shift labels left and up so they sit just inside the right edge of their line
    label_offset = mtransforms.offset_copy(ax.transData, fig=ax.figure, x=-8, y=2, units='points')

    # shift the start-balance label right and down so it sits just inside the left edge, below the line
    start_label_offset = mtransforms.offset_copy(ax.transData, fig=ax.figure, x=4, y=-5, units='points')
    plt.text(
        x_first, conf['balance'], f"${conf['balance']:,.0f}",
        fontsize=10,
        fontfamily='Monospace',
        verticalalignment='top',
        horizontalalignment='left',
        color='green',
        transform=start_label_offset
    )

    # 5th and 95th percentile markers (middle 90% of outcomes)
    p5  = mc_result_df.iloc[-1].quantile(0.05)
    p95 = mc_result_df.iloc[-1].quantile(0.95)
    p_offset = mtransforms.offset_copy(ax.transData, fig=ax.figure, x=8, y=0, units='points')
    ax.scatter(x_last, p95, marker='o', s=7**2, color='black', zorder=5)
    ax.scatter(x_last, p5,  marker='o', s=7**2, color='black', zorder=5)
    ax.text(x_last, p95, f"95% (${p95:,.0f})",
        fontsize=9, fontfamily='Monospace', verticalalignment='center',
        color='brown', transform=p_offset)
    ax.text(x_last, p5, f"5% (${p5:,.0f})",
        fontsize=9, fontfamily='Monospace', verticalalignment='center',
        color='brown', transform=p_offset)

    # from the startbalance and the Rmul average draw a straight line (y = ax + b)
    #risk_per_trade = risk * conf['balance']
    #a = float(risk_per_trade * Rmul_avg)
    #b = float(conf['balance'])
    #x_vals = np.array(mc_result_df.index)
    #y_vals = a * x_vals + b
    #ax.plot(x_vals, y_vals, color='blue', linewidth=2.0, linestyle='dotted', alpha=0.5)

    # add label for the last average value
    #y_last = a * x_last + b
    #plt.text(x_last, y_last, f"${y_last:,.0f}",
    #     fontsize=10,
    #     fontfamily='Monospace',
    #     verticalalignment='center',
    #     color='blue',
    #     transform=p_offset
    #)

    # annualized gain trading simulation (CAGR)
    median_balance = mc_result_df.iloc[-1].median()
    if stats.trades_len:
        ann_ret_sim = ann_return(conf['balance'], median_balance, stats.trades_len/365)
        sim_label = f"${median_balance:,.0f} ({ann_ret_sim:.1%})"
    else:
        sim_label = f"${median_balance:,.0f}"
    plt.text(
        x_last, median_balance, sim_label,
        fontsize=10,
        fontfamily='Monospace',
        verticalalignment='bottom',
        horizontalalignment='right',
        transform=label_offset
    )

    # plot the buy-and-hold benchmark, if provided
    if benchmark is not None:
        val_out, ann_ret_hodl = benchmark
        hodl_label = f"HODL ({conf.get('bm_ticker', 'URTH')})"

        ax.plot([x_first, x_last], [val_out, val_out], color='black', linewidth=1.5, linestyle='-.', alpha=.7, label=hodl_label)
        # Shift the HODL label to the left so its text never overlaps with the median label
        hodl_offset = mtransforms.offset_copy(ax.transData, fig=ax.figure, x=-110, y=2, units='points')
        plt.text(
            x_last, val_out, f"${val_out:,.0f} ({ann_ret_hodl:.1%})",
            fontsize=10,
            fontfamily='Monospace',
            verticalalignment='bottom',
            horizontalalignment='right',
            transform=hodl_offset
        )

    # choose between upper-right and lower-right for the trend-line legend,
    # based on which has fewer simulation paths passing through it
    if y_max > 0:
        _n = len(plot_df)
        _q = max(1, int(_n * 0.25))
        _d_right = plot_df.values[_n - _q:_n]
        _upper_density = np.sum((_d_right >= 0.70 * y_max) & (_d_right <= 1.00 * y_max))
        _lower_density = np.sum((_d_right >= 0.00 * y_max) & (_d_right <= 0.30 * y_max))
        _legend_loc = 'lower right' if _lower_density < _upper_density else 'upper right'
    else:
        _legend_loc = 'upper right'

    _legend_names = {'Median', f"HODL ({conf.get('bm_ticker', 'URTH')})"}
    _handles, _labels = ax.get_legend_handles_labels()
    _named = [(h, l) for h, l in zip(_handles, _labels) if l in _legend_names]
    if _named:
        _anchor_y = 0.0 if _legend_loc == 'lower right' else 1.0
        ax.legend(*zip(*_named), loc=_legend_loc, bbox_to_anchor=(0.95, _anchor_y),
                  fontsize=9, facecolor='white', framealpha=1.0)
    ax.set_xlabel('Trade')
    ax.set_ylabel('Balance (USD)')
    ax.grid(True, which='both', linestyle='dotted', alpha=0.5)

    plt.savefig(ctx.outpath("images", output_filename), dpi=150)
    plt.close()

def _get_capital_invested(row, conf, balance, total_equity, stats):
    ''' return the invested capital and the no. of units bought'''

    # capital allocated for this trade
    capital_per_trade = compute_position_size(conf, balance, total_equity, stats)

    # number of units for the position sizing strategy
    if conf["pos_sizing"] in {"core_equity_risk", "fixed_dollar_risk", "total_equity_risk"}:
        divisor = row.Risk
    else:
        divisor = row.Enter
    if divisor != 0.0:
        units = capital_per_trade / divisor
    else: 
        units = 0.0

    # apply fee (fee is a percentage of the gross transaction)
    fee = units * row.Enter * float(conf["trading_fee"]) / 100
    cap_invested = units * row.Enter - fee
    #logger.debug(f"Trading fee (enter): {fee:.2f} ({row.Ticker})")

    # cap the capital allocation to a maximum percentage of total equity
    max_cap = conf['max_alloc_frac'] * total_equity
    if cap_invested > max_cap:
        logger.warning(f"Investment exceeds {conf['max_alloc_frac'] * 100:.1f}% of equity, capping... ({row.Ticker})")
        units = max_cap / row.Enter
        fee = units * row.Enter * float(conf["trading_fee"]) / 100
        cap_invested = units * row.Enter - fee

    # do not enter trades where the invested amount is too low, and scale down if the investement requires > current balance
    if cap_invested < conf['min_invest']:
        logger.warning(f"Investment amount too low, not entering trade! ({row.Ticker})")
        units = 0
        cap_invested = 0
    elif balance < cap_invested:
        logger.warning(f"Required balance to low for investment amount, scaling down... ({row.Ticker})")
        units = balance / row.Enter
        fee = units * row.Enter * float(conf["trading_fee"]) / 100
        cap_invested = units * row.Enter - fee
        #logger.debug(f"Trading fee (scaled down): {fee:.2f} ({row.Ticker})")
        # re-apply the min_invest floor: a scale-down against a near-exhausted
        # balance can leave a negligible position (also covers units <= 0)
        if cap_invested < conf['min_invest']:
            logger.warning(f"Scaled-down investment below minimum, not entering trade! ({row.Ticker})")
            units = 0
            cap_invested = 0

    return units, cap_invested

def load_ohlc_cache(tickers, ctx):
    """
    Pre-load each ticker's raw OHLC CSV once, indexed by 'Date', so repeated
    per-row lookups (see get_total_invested_value) don't re-read from disk.
    """
    cache = {}
    for ticker in tickers:
        file_path = ctx.outpath(f"data/{ticker}_ohlc_raw.csv")
        try:
            df = pd.read_csv(file_path)
            cache[ticker] = df.set_index('Date')
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            cache[ticker] = None
    return cache

def get_total_invested_value(active_trades, date, ohlc_cache):
    """
    For each ticker in active_trades, look up the 'Open' price for the given date
    in the pre-loaded OHLC cache, and return the total value (units * enter price)
    summed over all tickers.
    """
    total_value = 0.0
    for ticker, units in active_trades.items():
        if units == 0:
            continue
        df = ohlc_cache.get(ticker)
        if df is None or date not in df.index:
            continue
        enter_price = df.at[date, 'Open']
        # Handle possible string values like '-' or NaN
        if isinstance(enter_price, (int, float)) and not pd.isna(enter_price):
            total_value += units * enter_price
        else:
            try:
                enter_price = float(enter_price)
                total_value += units * enter_price
            except Exception:
                pass  # skip if not a valid number
    return total_value

def save_trades_table(dframe, conf, ctx):
    ''' save the trades table to file '''
    dframe.sort_values(by='Enter', ascending=True, inplace=True)
    dframe.reset_index(drop=True, inplace=True)

    # to track system perfomance, add a rolling Rmul over the last 30 trades
    dframe['Rmul30'] = dframe['Rmul'].rolling(30).mean().round(2)

    logger.debug("\n%s", dframe)
    dframe.to_csv(ctx.outpath('tables', "trades_table.csv"), index=False)

    # save the R-multiples of all trades for later reuse (e.g. tst/simulator.py)
    dframe['Rmul'].to_csv(ctx.outpath('tables', "Rmul_trades.csv"), index=False)

    # save to pdf file
    dframe.index = dframe.index + 1
    dframe['Enter'] = pd.to_datetime(dframe['Enter'], errors='coerce').dt.strftime('%d-%m-%Y')
    dframe['Exit'] = pd.to_datetime(dframe['Exit'], format='%Y-%m-%d', errors='coerce').dt.strftime('%d-%m-%Y')
    dframe['Exit'] = dframe['Exit'].where(dframe['Exit'].notna(), "-")
    # MAE and MFE are kept in the CSV for analysis but dropped from the PDF to
    # avoid widening the printed trades table
    html = df_to_html(dframe.drop(columns=['MAE', 'MFE'], errors='ignore'))
    HTML(string=html).write_pdf(ctx.outpath("trades_table.pdf"))

def table_style_css(font_px: int = 10) -> str:
    ''' shared table look (borders, striping, header shading, monospace) used
    by every table rendered into a PDF report, so they stay visually consistent. '''

    return f"""
        table {{
            border-collapse: collapse;
            width: 100%;                 /* fill the printable width */
            table-layout: fixed;         /* forces columns to share space */
            word-wrap: break-word;       /* long words break */
            overflow-wrap: anywhere;    /* newer spec – works in WeasyPrint */
            font-family: Courier New;
            font-size: {font_px}px;
        }}

        th, td {{
            border: 1px solid #dddddd;
            padding: 6px;                /* tighter padding for dense tables */
            text-align: right;
            vertical-align: top;
        }}

        th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}

        tbody tr:nth-child(odd) {{background-color:#fafafa;}}

        td {{
            white-space: normal;
            word-break: break-all;
        }}
    """

def df_to_html(df,
               font_px: int = 10,
               page_width_mm: int = 297,   # A4 landscape width
               page_height_mm: int = 210,  # A4 landscape height
               margin_mm: int = 10,
               index: bool = True) -> str:
    css = f"""
        <style>
            @page {{
                size: {page_width_mm}mm {page_height_mm}mm;   /* landscape */
                margin: {margin_mm}mm;
            }}
            @bottom-center {{ content: "Page " counter(page); }}

            body {{
                #font-family: Arial, Helvetica, sans-serif;
                font-family: Courier New;
                font-size: {font_px}px;
                line-height: 1.4;
                /* Prevent accidental horizontal scrollbars in the PDF */
                overflow-x: hidden;
            }}

            {table_style_css(font_px)}
        </style>
    """
    html_table = df.to_html(border=0, index=index)
    return f"<html><head>{css}</head><body>{html_table}</body></html>"

def _get_benchmark_result(conf, ctx):

    # benchmark (HODL of the whole quote list) instead of a single ticker.
    if conf.get('bm_ticker', 'URTH') == 'quote-lst':
        if ctx.benchmark_df is None:
            ctx.benchmark_df = _build_basket_benchmark_df(conf, ctx)
        return ctx.benchmark_df['Net Value (incl. fee)'].sum()

    # get benchmark data (buy-and-hold result for conf['bm_ticker'])
    ticker = conf.get('bm_ticker', 'URTH')
    benchmark_df = pd.read_csv(ctx.outpath('data', f"{ticker}_ohlc_raw.csv"))
    benchmark_df = benchmark_df.dropna(subset=['Open', 'High', 'Low', 'Close'], how='all')
    price_in = benchmark_df['Close'].iloc[0]
    price_out = benchmark_df['Close'].iloc[-1]
    shares = conf['balance']/price_in
    return shares * price_out


def _build_basket_benchmark_df(conf, ctx):
    ''' build the equal-weight basket buy-and-hold breakdown as a DataFrame and log
        it as a table. The starting balance is split equally across all N tickers in
        the quote list; each is bought at its first valid close and sold at its last
        close, paying the trading fee once on the buy and once on the sell. The
        'Net Value (incl. fee)' column is the net amount returned per position
        (gross proceeds minus both fees); its sum is the benchmark's final value. '''

    with open(ctx.path(conf['quotefile'])) as f:
        tickers = list(json.loads(f.read()).keys())

    capital_per_stock = float(conf['balance']) / len(tickers)
    fee_frac = float(conf['trading_fee']) / 100

    rows = []
    buy_dates, sell_dates = [], []
    for idx, ticker in enumerate(tickers, start=1):
        df = pd.read_csv(ctx.outpath('data', f"{ticker}_ohlc_raw.csv"))
        df = df.dropna(subset=['Close'])
        price_in = df['Close'].iloc[0]
        price_out = df['Close'].iloc[-1]
        buy_dates.append(str(df['Date'].iloc[0]))
        sell_dates.append(str(df['Date'].iloc[-1]))
        units = capital_per_stock / price_in
        buy_fee = capital_per_stock * fee_frac
        gross_out = units * price_out
        sell_fee = gross_out * fee_frac
        net = gross_out - buy_fee - sell_fee
        rows.append({'#': idx, 'Ticker': ticker, 'Buy': price_in, 'Invested': capital_per_stock,
                     'Units': units, 'Sell': price_out, 'Net Value (incl. fee)': net})

    bm_df = pd.DataFrame(rows, columns=['#', 'Ticker', 'Buy', 'Invested', 'Units', 'Sell', 'Net Value (incl. fee)'])
    # overall span across the basket (earliest buy, latest sell), surfaced as a
    # sub-header row in the report so the spanned timeframe is visible
    bm_df.attrs['buy_date'] = min(buy_dates) if buy_dates else ''
    bm_df.attrs['sell_date'] = max(sell_dates) if sell_dates else ''
    logger.debug(f"Quote list benchmark ({len(tickers)}):\n" +
                 bm_df.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    logger.debug(f"Quote list benchmark final value: {bm_df['Net Value (incl. fee)'].sum():,.2f}")
    return bm_df


def _series_max_drawdown_pct(values):
    ''' maximum peak-to-trough decline of a value series, as a positive
        percentage (0.0 means the series never dipped below a prior peak). '''
    peak = float('-inf')
    max_dd = 0.0
    for v in values:
        if v is None:
            continue
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd * 100.0


def _strategy_drawdown_pct(ctx):
    ''' max drawdown of the simulated account over the holding period, from the
        mark-to-market Value curve in trades_list.csv, ending on the final
        liquidated balance (mirrors the equity curve in styled_balance_plot). '''
    try:
        tl = pd.read_csv(ctx.outpath('tables', 'trades_list.csv'))
    except Exception as e:
        logger.debug(f"strategy drawdown: cannot read trades_list.csv ({e})")
        return None
    vals = pd.to_numeric(tl['Value'], errors='coerce').dropna().tolist()
    bal = pd.to_numeric(tl['Balance'], errors='coerce').dropna()
    if len(bal):
        vals.append(float(bal.iloc[-1]))
    return _series_max_drawdown_pct(vals) if vals else None


def _benchmark_drawdown_pct(conf, ctx):
    ''' max drawdown of the buy-and-hold benchmark over the holding period: the
        single ticker's close path, or the equal-weight basket's aggregate
        mark-to-market value when bm_ticker == 'quote-lst'. '''
    bm_ticker = conf.get('bm_ticker', 'URTH')
    try:
        if bm_ticker == 'quote-lst':
            with open(ctx.path(conf['quotefile'])) as f:
                tickers = list(json.loads(f.read()).keys())
            capital_per_stock = float(conf['balance']) / len(tickers)
            series = []
            for ticker in tickers:
                df = pd.read_csv(ctx.outpath('data', f"{ticker}_ohlc_raw.csv")).dropna(subset=['Close'])
                units = capital_per_stock / df['Close'].iloc[0]
                series.append(pd.Series((units * df['Close']).values,
                                        index=pd.to_datetime(df['Date'], errors='coerce')))
            mat = pd.concat(series, axis=1).sort_index()
            # before a ticker's first close it is held as cash (its equal
            # allocation); carry the last known value forward over any gaps
            mat = mat.ffill().fillna(capital_per_stock)
            return _series_max_drawdown_pct(mat.sum(axis=1).tolist())
        sdf = pd.read_csv(ctx.outpath('data', f"{bm_ticker}_ohlc_raw.csv")).dropna(subset=['Close'])
        return _series_max_drawdown_pct(sdf['Close'].tolist())
    except Exception as e:
        logger.debug(f"benchmark drawdown: skipped ({e})")
        return None


def _benchmark_equity_series(conf, ctx, calendar):
    ''' the buy-and-hold benchmark's daily mark-to-market value, reindexed onto
        the equity curve's master calendar so it can be drawn as a curve next to
        the strategy equity. Each mode mirrors its own final-value convention
        (see _get_benchmark_result / _build_basket_benchmark_df) so the curve's
        last point ties out exactly to the flat "Buy & hold" line:

        - single ticker: fee-less, the whole balance bought at the first close;
        - quote-lst basket: equal-weight, buy fee deducted from the moment each
          ticker is bought and sell fee added at that ticker's own last close,
          with the net proceeds carried forward as cash. Before a ticker's first
          close its equal allocation is held as cash.

        Returns a pd.Series indexed by `calendar` (a DatetimeIndex), or None. '''
    bm_ticker = conf.get('bm_ticker', 'URTH')
    try:
        if bm_ticker == 'quote-lst':
            with open(ctx.path(conf['quotefile'])) as f:
                tickers = list(json.loads(f.read()).keys())
            capital_per_stock = float(conf['balance']) / len(tickers)
            fee_frac = float(conf['trading_fee']) / 100
            series = []
            for ticker in tickers:
                df = pd.read_csv(ctx.outpath('data', f"{ticker}_ohlc_raw.csv")).dropna(subset=['Close'])
                units = capital_per_stock / df['Close'].iloc[0]
                buy_fee = capital_per_stock * fee_frac
                # mark to market net of the buy fee already paid
                v = pd.Series((units * df['Close']).values - buy_fee,
                              index=pd.to_datetime(df['Date'], errors='coerce'))
                # sell fee is booked on this ticker's own last close; carried
                # forward as net cash for the rest of the period by the ffill below
                v.iloc[-1] -= (units * df['Close'].iloc[-1]) * fee_frac
                series.append(v)
            mat = pd.concat(series, axis=1).sort_index()
            mat = mat.reindex(mat.index.union(calendar)).ffill().reindex(calendar)
            # before a ticker's first close its allocation sits in cash
            mat = mat.fillna(capital_per_stock)
            return mat.sum(axis=1)

        sdf = pd.read_csv(ctx.outpath('data', f"{bm_ticker}_ohlc_raw.csv")).dropna(subset=['Close'])
        shares = float(conf['balance']) / sdf['Close'].iloc[0]   # fee-less, mirrors _get_benchmark_result
        v = pd.Series((shares * sdf['Close']).values,
                      index=pd.to_datetime(sdf['Date'], errors='coerce'))
        v = v.reindex(v.index.union(calendar)).ffill().reindex(calendar)
        # before the first close the whole balance is held as cash
        return v.fillna(float(conf['balance']))
    except Exception as e:
        logger.debug(f"benchmark equity curve: skipped ({e})")
        return None


def equity_plot(df, conf, ctx, max_recovery=0, rec_from=None, rec_to=None):
    ''' plot the daily equity curve produced by do_equity_simulation '''

    benchmark_enabled = conf.get('benchmark', True)
    val_out = _get_benchmark_result(conf, ctx) if benchmark_enabled else None

    if conf.get('report_style', 'styled') == 'styled':
        # the benchmark's daily value curve, aligned to the equity curve's
        # calendar (the Date column). Drawn only in the styled report.
        bm_curve = None
        if benchmark_enabled:
            calendar = pd.to_datetime(df['Date'], errors='coerce').dropna()
            bm_curve = _benchmark_equity_series(conf, ctx, pd.DatetimeIndex(calendar))
        rp.styled_equity_plot(df, conf, ctx, val_out, max_recovery, rec_from, rec_to,
                              bm_curve=bm_curve)
        return

    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Equity'] = pd.to_numeric(df['Equity'], errors='coerce')
    df['Trail1Y'] = pd.to_numeric(df['Trail1Y'], errors='coerce')
    df['MonthRet'] = pd.to_numeric(df['MonthRet'], errors='coerce')
    df = df.dropna(subset=['Date', 'Equity'])

    fig, (ax, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8.5), sharex=True,
                                       gridspec_kw={'height_ratios': [3, 1.6, 1.6]})
    fig.suptitle(f"Equity curve [{conf['pos_sizing']}]", fontsize=16)

    ax.plot(df['Date'], df['Equity'], color='green', linewidth=1.2, alpha=0.9, label='Equity')
    ax.axhline(y=conf['balance'], color='green', linewidth=.9, linestyle='--')
    if val_out is not None:
        ax.axhline(y=val_out, color='brown', linewidth=.9, linestyle='--', label='HODL')
    ax.set_ylabel('Equity (USD)')
    ax.legend(loc='upper left')

    if rec_from is not None and rec_to is not None:
        ax.text(0.98, 0.06, f"Longest drawdown: {max_recovery} days "
                f"({rec_from:%Y-%m-%d} - {rec_to:%Y-%m-%d})",
                transform=ax.transAxes, ha='right', va='bottom', color='gray', fontsize=9)

    roll = df.dropna(subset=['Trail1Y'])
    ax2.axhline(y=0, color='gray', linewidth=.9)
    ax2.plot(roll['Date'], roll['Trail1Y'], color='blue', linewidth=1.0)
    ax2.set_ylabel('Trailing 1y (USD)')

    months = df.dropna(subset=['MonthRet'])
    ax3.axhline(y=0, color='gray', linewidth=.9)
    ax3.bar(months['Date'], months['MonthRet'], width=22,
            color=['green' if v >= 0 else 'red' for v in months['MonthRet']])
    ax3.set_ylabel('Monthly (USD)')
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

    plt.savefig(ctx.outpath('images', 'equity_plot.png'), bbox_inches='tight')
    plt.close(fig)


def monthly_dist_plot(df, conf, ctx):
    ''' plot the distribution of the monthly returns from the equity table '''

    if conf.get('report_style', 'styled') == 'styled':
        rp.styled_monthly_dist_plot(df, ctx)
        return

    months = pd.to_numeric(df['MonthRet'], errors='coerce').dropna()
    if months.empty:
        logger.warning("No monthly returns to plot")
        return

    step = 1000.0
    bins = np.arange(np.floor(months.min() / step) * step,
                     np.ceil(months.max() / step) * step + step, step)

    fig = plt.figure(figsize=(10, 5))
    fig.suptitle("Monthly return distribution", fontsize=16)
    plt.hist(months[months >= 0], bins=bins, color='green', alpha=0.9, label='Positive months')
    plt.hist(months[months < 0], bins=bins, color='red', alpha=0.9, label='Negative months')
    plt.axvline(x=0, color='gray', linewidth=.9)
    mean = months.mean()
    plt.axvline(x=mean, color='blue', linewidth=2.0, linestyle='--', label='Mean')
    plt.gca().text(mean, 1.02, f"{mean:,.0f}", transform=plt.gca().get_xaxis_transform(),
                   ha='center', va='bottom', color='blue', fontsize=9)
    plt.gca().text(0.02, 0.95, "Max.\nMin.\nStd.", transform=plt.gca().transAxes,
                   ha='left', va='top', color='gray', fontsize=9)
    plt.gca().text(0.16, 0.95, f"{months.max():,.0f}\n{months.min():,.0f}\n{months.std():,.0f}",
                   transform=plt.gca().transAxes, ha='right', va='top', color='gray', fontsize=9)
    plt.xlabel('Monthly return (USD)')
    plt.ylabel('Number of months')
    plt.legend(loc='upper right')
    plt.savefig(ctx.outpath('images', 'monthly_dist_plot.png'), bbox_inches='tight')
    plt.close(fig)


def balance_plot(df, conf, ctx):
    ''' plot paper trading simulation results '''

    benchmark_enabled = conf.get('benchmark', True)
    val_out = _get_benchmark_result(conf, ctx) if benchmark_enabled else None

    if conf.get('report_style', 'styled') == 'styled':
        rp.styled_balance_plot(df, conf, ctx, val_out)
        return

    fig = plt.figure(figsize = (10, 5))
    plot_title = f"Trading simulation [{conf['pos_sizing']}]"
    fig.suptitle(plot_title, fontsize=16)
    
    plt.plot(df.index, df['Balance'],
            color='brown', linewidth=0.7, alpha=0.7,
            label='Balance', linestyle='--')

    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
    plt.plot(df.index, df['Value'],
            color='green', linewidth=2, alpha=0.9,
            label='Value')

    plt.axhline(y=conf['balance'], color='green', linewidth=.9, linestyle='--')

    bal_str = f"TRADE: ${df.iloc[-1]['Balance']:,.0f}"
    if benchmark_enabled:
        bal_str = f" HODL: ${val_out:,.0f}\n" + bal_str
    plt.text(
        0.75, 0.22, bal_str,
        transform=plt.gca().transAxes,
        fontsize=14,
        fontfamily='Monospace', 
        verticalalignment='top',
        bbox=dict(
            facecolor='white',
            alpha=0.7,
            boxstyle='round,pad=0.5',
            edgecolor='gray'
        )
    )

    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
    first_date = df['Date'].iloc[0]
    last_date  = df['Date'].iloc[-1]
    date_fmt   = "%d-%m-%Y"

    plt.annotate(
        first_date.strftime(date_fmt),
        xy=(0, 1.0), xycoords='axes fraction',
        xytext=(40, 15),
        textcoords='offset points',
        fontsize=12,
        ha='center', va='top'
    )
    plt.annotate(
        last_date.strftime(date_fmt),
        xy=(1.0, 1.0), xycoords='axes fraction',
        xytext=(-40, 15),
        textcoords='offset points',
        fontsize=12,
        ha='center', va='top'
    )

    # '-' values found in 'Enter' are actually exit points. '-' in 'Exit' are entry points
    if df['Enter'].value_counts().any():
        df['Enter'] = df['Enter'].map({'-': 0})
        plt.scatter(df.index, df['Enter'], color='darkred', label='Exit', marker='v', alpha = 1)
    if df['Exit'].value_counts().any():
        df['Exit'] = df['Exit'].map({'-': 0})
        plt.scatter(df.index, df['Exit'], color='green', label='Enter', marker='^', alpha = 1)

    plt.grid(linestyle='--')
    plt.ylabel('Balance (USD)')
    plt.legend(loc='upper left')
    plt.savefig(ctx.outpath("images", "balance_plot.png"), dpi=150)
    plt.close(fig)

def mae_scatter_plot(trades_df, conf, ctx):
    ''' standalone plot: MAE (R) vs R-multiple per closed trade, to
    help choose the stop distance. Not part of either report variant, so it
    always uses the report palette. See rp.styled_mae_scatter_plot. '''
    rp.styled_mae_scatter_plot(trades_df, conf, ctx)

def mfe_mae_scatter_plot(trades_df, conf, ctx):
    ''' standalone plot: MFE vs MAE per closed trade, both in R, to
    show how much of each trade's favorable run was actually kept. Not part of
    either report variant, so it always uses the report palette. See
    rp.styled_mfe_mae_scatter_plot. '''
    rp.styled_mfe_mae_scatter_plot(trades_df, conf, ctx)

def trades_plot(trades_lst, Rmul30_lst, sys_stats, conf, ctx, stats):
    ''' plot trades histograms '''

    if conf.get('report_style', 'styled') == 'styled':
        rp.styled_trades_plot(trades_lst, Rmul30_lst, ctx)
        rp.styled_distribution_plot(trades_lst, ctx)
        return

    trades_tot = len(trades_lst)
    pos_cnt = sum(1 for value in trades_lst if value > 0)
    neg_cnt = sum(1 for value in trades_lst if value < 0)

    Ravg = st.mean(trades_lst)
    SysQ = stats.sqn

    xs = np.arange(len(trades_lst))
    fig = plt.figure(figsize = (10, 5))
    fig.suptitle('Trades vs. R-multiple', fontsize=16)
    plt.bar(xs, trades_lst, color='brown', width=0.75)
    plt.plot(xs, Rmul30_lst, color='blue', linewidth=1.5, alpha=.7, linestyle='-', label='Rmul30')
    plt.legend(loc='upper left')

    plt.ylabel('R-multiple')
    plt.grid(True, color='grey', linewidth=.5, linestyle='dashed')

    plt.text(
        0.67, 0.95, sys_stats,
        transform=plt.gca().transAxes,
        fontsize=7,
        fontfamily='Monospace', 
        verticalalignment='top',
        bbox=dict(facecolor='white', alpha=0.9, boxstyle='round,pad=0.5', edgecolor='gray')
    )

    plt.savefig(ctx.outpath("images", "system_trades_plot.png"), dpi=150)
    plt.close(fig)

    sns.set_style("white")
    fig = plt.figure(figsize = (10, 5))
    fig.suptitle(f"Trades distribution [{trades_tot} trades (+{pos_cnt}|-{neg_cnt})]", fontsize=16)

    df = pd.DataFrame(trades_lst, columns=['Trades'])

    df['Sign'] = df['Trades'].apply(lambda x: 'Positive' if x >= 0 else 'Negative')
    palette = {'Positive': "#22d63a",
               'Negative': "#db1717"}
    
    bins_rice = int(np.ceil(2 * trades_tot ** (1/2)))
    ax = sns.histplot(
        data=df,
        x='Trades',
        hue='Sign',
        palette=palette,
        element='bars',
        stat='count',
        kde=False,
        bins=bins_rice,
        alpha=0.6
    )
    ax.get_legend().remove()

    mean_val = st.mean(trades_lst)
    col = 'green' if mean_val > 0 else 'red'
    ax.axvline(mean_val, color=col, linestyle='-.', linewidth=2, alpha=.7)
    ax.set_xlabel('R-multiple')
    ax.grid(linestyle='--')

    ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    sys_str = (
        f"R-average: {Ravg:,.2f} {get_rmean_qlabel(Ravg)}\n"
        f"SQN      : {SysQ:,.2f} {get_system_qlabel(SysQ)}\n"
        f"Win Rate : {stats.win_rate:.0f}%"
    )
    plt.text(
        0.60, 0.95, sys_str,
        transform=plt.gca().transAxes,
        fontsize=12,
        fontfamily='Monospace', 
        verticalalignment='top',
        bbox=dict(
            facecolor='white',
            alpha=0.7,
            boxstyle='round,pad=0.5',
            edgecolor='gray'
        )
    )

    plt.savefig(ctx.outpath("images", "system_trades_dist_plot.png"), dpi=150)
    plt.close(fig)

def _plot_price_overlays(ax, df, conf):
    ''' draws the price-panel TA overlays (BB/SMA225/EMA/SMA/CE) + Close + Enter/Exit markers.
        Shared by ticker_plot and ticker_plot_ta so the two stay in sync. '''
    plot_indicators = conf.get('plot_indicators', [])

    if conf['enter'] == 'BBRSI' or 'BB' in plot_indicators:
        ax.plot(df.index, df[['BBu', 'BBl','BBm']], color='black', linewidth=.1)
        ax.fill_between(df.index, df['BBl'], df['BBu'], color='grey', alpha=.05)

    if 'SMA225' in plot_indicators:
        # SMA 45wk indicator of bear/bull stock market
        ax.plot(df.index, df['SMA225'], color='orange', linewidth=2, linestyle='-.', label='SMA225')

    if conf['enter'] == 'DONCH' or 'DON' in plot_indicators:
        ax.plot(df.index, df['DONup'], color='green', linewidth=.6, linestyle='--', label='DONup')
        ax.plot(df.index, df['DONdn'], color='brown', linewidth=.6, linestyle='--', label='DONdn')
        ax.fill_between(df.index, df['DONdn'], df['DONup'], color='grey', alpha=.05)

    if conf['enter'] == '3EMA':
        ax.plot(df.index, df['EMAfast'], color='green', linewidth=.5, label=f"EMA{conf['ema_fast']}")
        ax.plot(df.index, df['EMAmid'], color='brown', linewidth=.5, label=f"EMA{conf['ema_mid']}")
        ax.plot(df.index, df['EMAslow'], color='black', linewidth=.5, label=f"EMA{conf['ema_slow']}")

    if conf['enter'] == 'SMA':
        ax.plot(df.index, df['SMAfast'], color='green', linewidth=.5, label=f"SMA{conf['sma_fast']}")
        ax.plot(df.index, df['SMAslow'], color='brown', linewidth=.5, label=f"SMA{conf['sma_slow']}")

    if conf['exit'] == 'CE':
        ax.plot(df.index, df['CE'], color='black', linewidth=.5, linestyle='--', label='CEexit')
    if conf['exit'] == 'CEE':
        ax.plot(df.index, df['CE'], color='black', linewidth=.5, linestyle='--', label='CEexit')
        ax.plot(df.index, df['CE2'], color='brown', linewidth=.5, linestyle='--', label='CE2exit')
        ax.plot(df.index, df['CE15'], color='yellow', linewidth=.5, linestyle='--', label='CE15exit')

    ax.plot(df.index, df['Close'], color='red', linewidth=.8, label='Close')

    if df['Enter'].value_counts().any():
        ax.scatter(df.index, df['Enter'], color='green', label='Enter', marker='^', alpha=1)
    if df['Exit'].value_counts().any():
        ax.scatter(df.index, df['Exit'], color='darkred', label='Exit', marker='v', alpha=1)

def plot_benchmark_price(df, ticker, description, conf, ctx):
    ''' plot a plain Close-price chart without any trading signals, used both for
        the auto-injected benchmark ticker (which never runs through the strategy
        pipeline) and for follow_only mode. Draws the configured
        plot_indicators overlay (SMA225 bull/bear line and/or Bollinger Bands) as
        a visual aid, matching the overlays on the traded tickers' charts. '''

    if conf.get('report_style', 'styled') == 'styled':
        rp.styled_benchmark_price(df, ticker, description, conf, ctx)
        return

    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)

    fig = plt.figure(figsize = (28, 10))
    ax = fig.gca()
    fig.suptitle('{} ({})'.format(description, ticker), fontsize=20)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m-%Y'))

    plot_indicators = conf.get('plot_indicators', [])

    if 'BB' in plot_indicators:
        # reuse the precomputed Bollinger columns when the caller passed a
        # processed frame (follow_only), else compute them here (the
        # auto-injected benchmark is charted straight from raw OHLC)
        if 'BBu' in df.columns:
            bbu, bbm, bbl = df['BBu'], df['BBm'], df['BBl']
        else:
            bbu, bbm, bbl = ta.BBANDS(df['Close'], timeperiod=20, matype=0)
        ax.plot(df.index, bbu, color='black', linewidth=.1)
        ax.plot(df.index, bbm, color='black', linewidth=.1)
        ax.plot(df.index, bbl, color='black', linewidth=.1)
        ax.fill_between(df.index, bbl, bbu, color='grey', alpha=.05)

    if 'SMA225' in plot_indicators:
        sma225 = df['SMA225'] if 'SMA225' in df.columns else ta.SMA(df['Close'], timeperiod=225)
        ax.plot(df.index, sma225, color='orange', linewidth=2, linestyle='-.', label='SMA225')

    if 'DON' in plot_indicators:
        donup = df['DONup'] if 'DONup' in df.columns else df['High'].rolling(conf['donch_enter']).max().shift(1)
        dondn = df['DONdn'] if 'DONdn' in df.columns else df['Low'].rolling(conf['donch_exit']).min().shift(1)
        ax.plot(df.index, donup, color='green', linewidth=.6, linestyle='--', label='DONup')
        ax.plot(df.index, dondn, color='brown', linewidth=.6, linestyle='--', label='DONdn')
        ax.fill_between(df.index, dondn, donup, color='grey', alpha=.05)

    ax.plot(df.index, df['Close'], color='red', linewidth=.8, label='Close')
    plt.text(df.tail(1).index.item(), df.iloc[-1]['Close'], '{:,.2f}'.format(df.iloc[-1]['Close']))

    plt.grid(linestyle='--')
    plt.xlabel('Date')
    plt.ylabel('Price (USD)')
    plt.legend(loc='lower right')
    plt.savefig(ctx.outpath("plots", f"{ticker}_plot.png"), dpi=150)
    plt.close(fig)

def ticker_plot(df, ticker, description, conf, ctx):
    ''' plot ticker + enter and exits points '''

    if conf.get('report_style', 'styled') == 'styled':
        rp.styled_ticker_plot(df, ticker, description, conf, ctx)
        return

    fig = plt.figure(figsize = (28, 10))
    ax = fig.gca()
    
    # Ensure index is datetime
    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)

    fig.suptitle('{} ({})'.format(description, ticker), fontsize=20)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=conf['date_int']))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m-%Y'))

    plt.text(df.tail(1).index.item(), df.iloc[-1]['Close'], '{:,.2f}'.format(df.iloc[-1]['Close']))
    #plt.text(df.tail(1).index.item(), df.iloc[-1]['CE'], '{:,.2f}'.format(df.iloc[-1]['CE']), alpha=.5)

    _plot_price_overlays(ax, df, conf)

    col = 'gray'
    Rstr = ""
    if df.iloc[-1]['Signal'] == 'ENTER':
        col = 'green'
    elif (df.iloc[-1]['Signal'] == 'STOPLOSS') or (df.iloc[-1]['Signal'] == 'EXIT' and df.iloc[-1]['Rmul'] <= 0):
        col = 'red'
        Rstr = '({:,.1f}R)'.format(df.iloc[-1]['Rmul'])
    elif df.iloc[-1]['Signal'] == 'EXIT':
        col = 'green'
        Rstr = '({:,.1f}R)'.format(df.iloc[-1]['Rmul'])
    plt.annotate('Signal: {} {}'.format(df.iloc[-1]['Signal'], Rstr), xy=(0.01, 1), xycoords='axes fraction', fontsize=22, xytext=(0,-20), 
                     bbox={'facecolor':col, 'boxstyle':'square', 'alpha':0.1}, textcoords='offset points', ha='left', va='top')

    # floating date
    ax.annotate(
        df.tail(1).index.item().strftime('%a %d %b %Y'),
        xy=(0.94, 1.0), xycoords='axes fraction',
        xytext=(0, 35),
        textcoords='offset points',
        fontsize=20,
        ha='center', va='top'
    )

    enter = df.iloc[-1]['PriceIn']
    stoploss = df.iloc[-1]['STLoss']
    risk = df.iloc[-1]['Risk']
    profit = df.iloc[-1]['Profit']
    Rmul = 0.0
    if (risk != 0):
        Rmul = profit/risk
    plt.annotate('{} days, enter: {:,.2f}, stoploss: {:,.2f}, risk: {:,.2f}, profit: {:,.2f} ({:,.1f}R)'.format(int(df.iloc[-1]['InTrade']), 
                 enter, stoploss, risk, profit, Rmul), xy=(0.93, 0), xycoords='axes fraction', fontsize=16, xytext=(0, 25),
                 textcoords='offset points', ha='right', va='top')

    if 'Rmul' in df.columns:
        trades_count = df['Rmul'].count()
        r_avg = df['Rmul'].sum() / trades_count if trades_count else 0.0
        plt.annotate('R-average: {:,.2f} ({} trades)'.format(r_avg, trades_count),
                     xy=(0.01, 0), xycoords='axes fraction', fontsize=22, xytext=(0,35),
                     bbox={'facecolor':'0.9', 'boxstyle':'square', 'alpha':0.2}, textcoords='offset points', ha='left', va='top')

    plt.grid(linestyle='--')
    plt.xlabel('Date')
    plt.ylabel('Price (USD)')
    plt.legend(loc='lower right')
    plt.savefig(ctx.outpath("plots", f"{ticker}_plot.png"), dpi=150)
    plt.close(fig)

def ticker_plot_ta(df, ticker, description, conf, ctx):
    ''' plot ticker +ta indicators + enter and exits points '''

    if conf.get('report_style', 'styled') == 'styled':
        rp.styled_ticker_plot_ta(df, ticker, description, conf, ctx)
        return

    bbrsi = conf['enter'] == 'BBRSI'
    macd = conf['enter'] == 'MACD'
    donch = conf['enter'] == 'DONCH'
    if bbrsi or macd:
        fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize = (28, 10))
    else:
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True, figsize = (28, 15))
    fig.suptitle('{} ({})'.format(description, ticker), fontsize=20)

    # Ensure index is datetime
    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)

    fig.gca().xaxis.set_major_locator(mdates.DayLocator(interval=conf['date_int']))
    fig.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    ax1.text(df.tail(1).index.item(), df.iloc[-1]['Close'], '{:,.2f}'.format(df.iloc[-1]['Close']))
    #ax1.text(df.tail(1).index.item(), df.iloc[-1]['CE'], '{:,.2f}'.format(df.iloc[-1]['CE']), alpha=.5)

    _plot_price_overlays(ax1, df, conf)

    col = 'gray'
    Rstr = ""
    if df.iloc[-1]['Signal'] == 'ENTER':
        col = 'green'
    elif (df.iloc[-1]['Signal'] == 'STOPLOSS') or (df.iloc[-1]['Signal'] == 'EXIT' and df.iloc[-1]['Rmul'] <= 0):
        col = 'red'
        Rstr = '({:,.1f}R)'.format(df.iloc[-1]['Rmul'])
    elif df.iloc[-1]['Signal'] == 'EXIT':
        col = 'green'
        Rstr = '({:,.1f}R)'.format(df.iloc[-1]['Rmul'])
    ax1.annotate('Signal: {} {}'.format(df.iloc[-1]['Signal'], Rstr), xy=(0.01, 1), xycoords='axes fraction', fontsize=22, xytext=(0,-20), 
                     bbox={'facecolor':col, 'boxstyle':'square', 'alpha':0.1}, textcoords='offset points', ha='left', va='top')

    # floating date
    ax1.annotate(
        df.tail(1).index.item().strftime('%a %d %b %Y'),
        xy=(0.94, 1.0), xycoords='axes fraction',
        xytext=(0, 35),
        textcoords='offset points',
        fontsize=20,
        ha='center', va='top'
    )

    if bbrsi:
        ax2.plot(df.index, df['RSI'], color='blue', linewidth=.8, label='RSI')
        ax2.axhline(y=conf['rsi_low'], color='red', linewidth=1, linestyle='-.')
        ax2.axhline(y=conf['rsi_high'], color='red', linewidth=1, linestyle='-.')
        ax2.fill_between(df.index, conf['rsi_low'], df['RSI'], color='grey', alpha=.1)
        ax2.set_ylabel('RSI')
    elif macd:
        hist_colors = np.where(df['MACDhist'] >= 0, 'green', 'red')
        ax2.bar(df.index, df['MACDhist'], color=hist_colors, width=1, alpha=.6, label='Histogram')
        ax2.plot(df.index, df['MACD'], color='blue', linewidth=.8, label='MACD')
        ax2.plot(df.index, df['MACDsig'], color='orange', linewidth=.8, label='Signal')
        ax2.axhline(y=0, color='black', linewidth=1, linestyle='--')
        ax2.set_ylabel('MACD')
    elif donch:
        ax2.plot(df.index, df['ATR'], color='blue', linewidth=.8, label='ATR')
        ax2.set_ylabel('ATR')

        ax3.plot(df.index, df['ADX'], color='blue', linewidth=.8, label='ADX')
        ax3.axhline(y=conf['adx_trend'], color='red', linewidth=1, linestyle='-.')
        ax3.set_ylabel('ADX')
    else:
        ax2.plot(df.index, df['ADX'], color='blue', linewidth=.8, label='ADX')
        ax2.axhline(y=conf['adx_trend'], color='red', linewidth=1, linestyle='-.')
        ax2.set_ylabel('ADX')

        # Directional Indicators (+DI and -DI)
        ax3.plot(df.index, df['P_DI'], color='green', linewidth=.8, label='POS_DI')
        ax3.plot(df.index, df['M_DI'], color='brown', linewidth=.8, label='NEG_DI')

    enter = df.iloc[-1]['PriceIn']
    stoploss = df.iloc[-1]['STLoss']
    risk = df.iloc[-1]['Risk']
    profit = df.iloc[-1]['Profit']
    Rmul = 0.0
    if (risk != 0):
        Rmul = profit/risk
    ax1.annotate('{} days, enter: {:,.2f}, stoploss: {:,.2f}, risk: {:,.2f}, profit: {:,.2f} ({:,.1f}R)'.format(int(df.iloc[-1]['InTrade']), 
                 enter, stoploss, risk, profit, Rmul), xy=(0.93, 0), xycoords='axes fraction', fontsize=16, xytext=(0, 25),
                 textcoords='offset points', ha='right', va='top')

    if 'Rmul' in df.columns:
        trades_count = df['Rmul'].count()
        r_avg = df['Rmul'].sum() / trades_count if trades_count else 0.0
        ax1.annotate('R-average: {:,.2f} ({} trades)'.format(r_avg, trades_count),
                     xy=(0.01, 0), xycoords='axes fraction', fontsize=22, xytext=(0,35),
                     bbox={'facecolor':'0.9', 'boxstyle':'square', 'alpha':0.2}, textcoords='offset points', ha='left', va='top')

    ax1.grid(linestyle='--')
    ax2.grid(linestyle='--')
    plt.xlabel('Date')
    ax1.set_ylabel('Price(USD)')
    ax1.legend(loc='lower right')
    ax2.legend(loc='lower right')
    if not (bbrsi or macd):
        ax3.grid(linestyle='--')
        ax3.legend(loc='lower right')
    plt.savefig(ctx.outpath("plots/TA", f"{ticker}_plot_ta.png"), dpi=150)
    plt.close(fig)

def ticker_plot_ta_custom(df, ticker, description, conf, ctx):
    ''' ad-hoc plot: price panel + one stacked panel per conf['ta_custom'] entry '''

    if conf.get('report_style', 'styled') == 'styled':
        rp.styled_ticker_plot_ta_custom(df, ticker, description, conf, ctx)
        return

    panels = conf['ta_custom']
    num_axes = 1 + len(panels)
    fig, axes = plt.subplots(num_axes, 1, sharex=True, figsize=(28, 5 * num_axes))
    fig.suptitle('{} ({})'.format(description, ticker), fontsize=20)

    # Ensure index is datetime
    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)

    axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=conf['date_int']))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    ax1 = axes[0]
    ax1.text(df.tail(1).index.item(), df.iloc[-1]['Close'], '{:,.2f}'.format(df.iloc[-1]['Close']))

    _plot_price_overlays(ax1, df, conf)

    col = 'gray'
    Rstr = ""
    if df.iloc[-1]['Signal'] == 'ENTER':
        col = 'green'
    elif (df.iloc[-1]['Signal'] == 'STOPLOSS') or (df.iloc[-1]['Signal'] == 'EXIT' and df.iloc[-1]['Rmul'] <= 0):
        col = 'red'
        Rstr = '({:,.1f}R)'.format(df.iloc[-1]['Rmul'])
    elif df.iloc[-1]['Signal'] == 'EXIT':
        col = 'green'
        Rstr = '({:,.1f}R)'.format(df.iloc[-1]['Rmul'])
    ax1.annotate('Signal: {} {}'.format(df.iloc[-1]['Signal'], Rstr), xy=(0.01, 1), xycoords='axes fraction', fontsize=22, xytext=(0,-20),
                     bbox={'facecolor':col, 'boxstyle':'square', 'alpha':0.1}, textcoords='offset points', ha='left', va='top')

    # floating date
    ax1.annotate(
        df.tail(1).index.item().strftime('%a %d %b %Y'),
        xy=(0.94, 1.0), xycoords='axes fraction',
        xytext=(0, 35),
        textcoords='offset points',
        fontsize=20,
        ha='center', va='top'
    )

    enter = df.iloc[-1]['PriceIn']
    stoploss = df.iloc[-1]['STLoss']
    risk = df.iloc[-1]['Risk']
    profit = df.iloc[-1]['Profit']
    Rmul = 0.0
    if (risk != 0):
        Rmul = profit/risk
    ax1.annotate('{} days, enter: {:,.2f}, stoploss: {:,.2f}, risk: {:,.2f}, profit: {:,.2f} ({:,.1f}R)'.format(int(df.iloc[-1]['InTrade']),
                 enter, stoploss, risk, profit, Rmul), xy=(0.93, 0), xycoords='axes fraction', fontsize=16, xytext=(0, 25),
                 textcoords='offset points', ha='right', va='top')

    if 'Rmul' in df.columns:
        ax1.annotate('R-average: {:,.2f} ({} trades)'.format(df['Rmul'].sum()/df['Rmul'].count(), df['Rmul'].count()),
                     xy=(0.01, 0), xycoords='axes fraction', fontsize=22, xytext=(0,35),
                     bbox={'facecolor':'0.9', 'boxstyle':'square', 'alpha':0.2}, textcoords='offset points', ha='left', va='top')

    ax1.set_ylabel('Price(USD)')

    for ax, name in zip(axes[1:], panels):
        if name == 'RSI':
            ax.plot(df.index, df['RSI'], color='blue', linewidth=.8, label='RSI')
            ax.axhline(y=conf['rsi_low'], color='red', linewidth=1, linestyle='-.')
            ax.axhline(y=conf['rsi_high'], color='red', linewidth=1, linestyle='-.')
            ax.fill_between(df.index, conf['rsi_low'], df['RSI'], color='grey', alpha=.1)
            ax.set_ylabel('RSI')
        elif name == 'ADX':
            ax.plot(df.index, df['ADX'], color='blue', linewidth=.8, label='ADX')
            ax.axhline(y=conf['adx_trend'], color='red', linewidth=1, linestyle='-.')
            ax.set_ylabel('ADX')
        elif name == 'DI':
            ax.plot(df.index, df['P_DI'], color='green', linewidth=.8, label='POS_DI')
            ax.plot(df.index, df['M_DI'], color='brown', linewidth=.8, label='NEG_DI')
            ax.set_ylabel('DI')
        elif name == 'MACD':
            hist_colors = np.where(df['MACDhist'] >= 0, 'green', 'red')
            ax.bar(df.index, df['MACDhist'], color=hist_colors, width=1, alpha=.6, label='Histogram')
            ax.plot(df.index, df['MACD'], color='blue', linewidth=.8, label='MACD')
            ax.plot(df.index, df['MACDsig'], color='orange', linewidth=.8, label='Signal')
            ax.axhline(y=0, color='black', linewidth=1, linestyle='--')
            ax.set_ylabel('MACD')
        elif name == 'ATR':
            ax.plot(df.index, df['ATR'], color='blue', linewidth=.8, label='ATR')
            ax.set_ylabel('ATR')
        elif name == 'OBV':
            ax.plot(df.index, df['OBV'], color='blue', linewidth=.8, label='OBV')
            ax.set_ylabel('OBV')
        elif name == 'FI':
            ax.plot(df.index, df['FI'], color='blue', linewidth=.8, label='FI')
            ax.axhline(y=0, color='black', linewidth=1, linestyle='--')
            ax.set_ylabel('FI')
        elif name == 'CCI':
            ax.plot(df.index, df['CCI'], color='blue', linewidth=.8, label='CCI')
            ax.axhline(y=100, color='red', linewidth=1, linestyle='-.')
            ax.axhline(y=-100, color='red', linewidth=1, linestyle='-.')
            ax.set_ylabel('CCI')
        elif name == 'ROC':
            ax.plot(df.index, df['ROC'], color='blue', linewidth=.8, label='ROC')
            ax.axhline(y=0, color='black', linewidth=1, linestyle='--')
            ax.set_ylabel('ROC')
        elif name == 'MFI':
            ax.plot(df.index, df['MFI'], color='blue', linewidth=.8, label='MFI')
            ax.axhline(y=80, color='red', linewidth=1, linestyle='-.')
            ax.axhline(y=20, color='red', linewidth=1, linestyle='-.')
            ax.set_ylabel('MFI')

    for ax in axes:
        ax.grid(linestyle='--')
        ax.legend(loc='lower right')

    plt.xlabel('Date')
    plt.savefig(ctx.outpath("plots/TA-custom", f"{ticker}_plot_ta_custom.png"), dpi=150)
    plt.close(fig)
