''' Utility functions for backtesting and TA operations '''

import sys
import math
import os
import re
import pandas as pd
import numpy as np
import seaborn as sns
import statistics as st
import requests
import random

from datetime import datetime
from typing import Dict, List

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator

import talib as ta
import yfinance as yf

import statsmodels.api as sm
from scipy import stats

from weasyprint import HTML

from telegram import Bot
from telegram.constants import ParseMode

from strategy import Stoploss, TradingSignals
from tables import TotalTradesList, TradesTable
from context import RunContext, SystemStats

# for concat of empty dataframe 
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

async def bot_signal_update(ctx, lastclose, snd_message):
    bot = Bot(token=ctx.bot_token)
    lastclose = lastclose.strftime('%a %d-%m-%Y')
    msg = f"<b>{lastclose}</b>\n<b>No. Ticker Close (Stoploss) Signal</b>\n<b>============================</b>\n{snd_message}"
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

def get_history_data(ticker, period=None, start=None, end=None):
    ''' 
    Available paramaters for the history() method are:
    period: data period to download (Either Use period parameter or use start and end) Valid periods are: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    interval: data interval (intraday data cannot extend last 60 days) Valid intervals are: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    start: If not using period - Download start date string (YYYY-MM-DD) or datetime.
    end: If not using period - Download end date string (YYYY-MM-DD) or datetime.
    prepost: Include Pre and Post market data in results? (Default is False)
    auto_adjust: Adjust all OHLC automatically? (Default is True)
    actions: Download stock dividends and stock splits events? (Default is True)
    '''

    download_kwargs = {
        "tickers": ticker,
        "interval": '1d',
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

    df = pd.DataFrame(raw_df, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df.set_index('Date', inplace=True)

    return raw_df

def get_quotes_data(quotes, conf, outfile, ctx):
    ''' download the quotes data '''
    config_str = '+++ downloading quotes (' + str(len(quotes)) + ')'
    print(config_str)
    idx = 1
    for ticker, desc in quotes.items():
        print(f'{idx} - {ticker}: {desc}\n', end='')
        idx += 1

        if conf.get("start") and conf.get("stop"):
            dfr = get_history_data(ticker, start=conf["start"], end=conf["end"])
        elif conf.get("start"):
            dfr = get_history_data(ticker, start=conf["start"])
        else:
            dfr = get_history_data(ticker, conf["interval"])

        dfr.to_csv(ctx.path('out/data',f"{ticker}_{outfile}"))

def add_technical_indicators(dframe, conf):
    ''' adds technical indicators as columns to the dataframe '''
    
    # Relative Strength Index (RSI)
    dframe['RSI'] = ta.RSI(dframe['Close'], timeperiod=conf['rsi_time'])

    # Average True Range (ATR)
    dframe['ATR'] = ta.ATR(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=conf['atr_time'])

    # Moving Average Convergence Devergence (MACD)
    #dframe['MACD'], dframe['MACDsig'], hist = ta.MACD(dframe['Close'], fastperiod=12, slowperiod=26, signalperiod=9)

    # Average Directional Movement Index (ADX)
    dframe['ADX'] = ta.ADX(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=14)

    # Directional Indicators (+DI and -DI)
    dframe['P_DI'] = ta.PLUS_DI(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=14)
    dframe['M_DI'] = ta.MINUS_DI(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=14)

    # On Balance Volume (OBV)
    #dframe['OBV'] = ta.OBV(dframe['Close'], dframe['Volume'])

    # Simple Moving Average (SMA)
    dframe['SMA50'] = ta.SMA(dframe['Close'], timeperiod=conf['sma_fast'])
    dframe['SMA200'] = ta.SMA(dframe['Close'], timeperiod=conf['sma_slow'])
   
    # Bear/Bull indcator (stock above = Bull, Stock below = Bear)
    dframe['SMA225'] = ta.SMA(dframe['Close'], timeperiod=225)

    # Triple Moving Average (3EMA) 20 50 100
    dframe['EMA20'] = ta.EMA(dframe['Close'], timeperiod=20)
    dframe['EMA50'] = ta.EMA(dframe['Close'], timeperiod=50)
    dframe['EMA100'] = ta.EMA(dframe['Close'], timeperiod=100)

    # Bollinger Bands (SMA) (default settings)
    dframe['BBu'], dframe['BBm'], dframe['BBl'] = ta.BBANDS(dframe['Close'], timeperiod=20, matype=0)

    # Chandelier Exit (CE)
    dframe['CEHigh'] = dframe['High'].rolling(22).max()
    atr22 = ta.ATR(dframe['High'], dframe['Low'], dframe['Close'], timeperiod=22)
    dframe['CE']  = dframe['CEHigh'] - atr22 * 3
    dframe['CE2'] = dframe['CEHigh'] - atr22 * 2
    dframe['CE15'] = dframe['CEHigh'] - atr22 * 1.5
    dframe.drop(['CEHigh'], axis=1, inplace=True)

    # Force Index (FI)
    #dframe['FI'] = dframe['Close'].diff(13) * dframe['Volume']

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

    intrade     = 0
    stoploss    = 0.0
    risk_oneR   = 0.0
    entry_atr   = 0.0
    entry_price = 0.0

    # trackers for MAE and MFE
    lowest_since_entry  = np.inf
    highest_since_entry = -np.inf

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

            # normalized MAE and MFE and E-Ratio
            if entry_atr != 0:
                mae = (entry_price - lowest_since_entry) / entry_atr
                mfe = (highest_since_entry - entry_price) / entry_atr
                mae_lst[i] = mae
                mfe_lst[i] = mfe
                eratio_lst[i] = mfe / mae if mae != 0 else np.nan
            else:
                mae_lst[i] = mfe_lst[i] = eratio_lst[i] = np.nan

        # ENTER signal
        if intrade == 0 and signals.check_enter_signal(row) == True:
            enter_lst[i] = row['Close']
            signal_lst[i] = "ENTER"

            intrade = 1
            stoploss = stloss.get_stoploss(row)
            risk_oneR = row['Close'] - stoploss
            entry_price = row["Close"]
            entry_atr   = row["ATR"]

            # update MFE and MAE
            lowest_since_entry  = entry_price
            highest_since_entry = entry_price

        # EXIT signal
        if intrade != 0 and (signals.check_exit_signal(row, intrade) or row['Close'] < stoploss):

            exit_lst[i] = row['Close']
            rmul_lst[i] = (row['Close'] - entry_price)/risk_oneR
            tlen_lst[i] = intrade

            if entry_atr != 0:
                mae = (entry_price - lowest_since_entry) / entry_atr
                mfe = (highest_since_entry - entry_price) / entry_atr
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
            entry_atr   = 0.0
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

    enter_lst, exit_lst, ticker_lst, pricein_lst, priceout_lst, risk_lst, duration_lst, \
        profit_lst, rmul_lst, signal_lst, lastclose_lst =  ([] for i in range(11))
    date_lst, tck_lst, buy_lst, sell_lst, oneR_lst, pprofit_lst =  ([] for i in range(6))

    for index, row in df.iterrows():
        
        if math.isnan(row['Enter']) == False:
            enter_lst.append(index)
            ticker_lst.append(ticker)
            price_in = row['Enter']
            pricein_lst.append(round(row['Enter'], 2))
            risk_lst.append(round(row['Risk'], 2))

            date_lst.append(index)
            tck_lst.append(ticker)
            buy_lst.append(row['Enter'])
            sell_lst.append("-")
            oneR_lst.append(round(row['Risk'], 2))
            pprofit_lst.append('-')

        if math.isnan(row['Exit']) == False:
            exit_lst.append(index)
            priceout_lst.append(round(row['Exit'], 2))
            profit_lst.append(round(row['Close'] - price_in, 2))
            rmul_lst.append(round(row['Rmul'], 2))
            duration_lst.append(int(round(row['TLen'], 0)))
            signal_lst.append(row['Signal'])
            lastclose_lst.append('-')

            date_lst.append(index)
            tck_lst.append(ticker)
            buy_lst.append("-")
            sell_lst.append(row['Exit'])
            oneR_lst.append("-")
            pprofit_lst.append(row['Close'] - price_in)

    # for open trades, fill in the empty fields
    if df['InTrade'].iloc[-1] != 0:
        exit_lst.append("-")
        priceout_lst.append("-")
        profit_lst.append(round(row['Profit'], 2))
        rmul_lst.append(round((row['Close']-row['PriceIn'])/row['Risk'], 2))
        duration_lst.append(int(round(row['InTrade'], 0)))
        signal_lst.append(row['Signal'])
        lastclose_lst.append(round(row['Close'], 2))

    trades_table.df['Enter']    = enter_lst
    trades_table.df['Exit']     = exit_lst
    trades_table.df['Ticker']   = ticker_lst
    trades_table.df['PriceIn']  = pricein_lst
    trades_table.df['PriceOut'] = priceout_lst
    trades_table.df['Risk']     = risk_lst
    trades_table.df['Length']   = duration_lst
    trades_table.df['Rmul']     = rmul_lst
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

def generate_system_stats(trades_df, trading_period, ctx, stats):
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
    win_perc  = float(100 * len(pos_lst) / num_trades)
    b = abs(pos_mean_r/neg_mean_r)
    kelly_criterion = (win_perc - ((1 - win_perc) / b)) / 100
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
        "+++ SYSTEM SUMMARY",
        f"+++ Length (days)     : {len_trades}",
        f"+++ Trades total      : {num_trades}",
        f"+++ Trades/yr         : {num_trades / (len_trades/365):.2f}",
        f"+++ R maximum         : {Rmax:,.2f}",
        f"+++ R minimum         : {Rmin:,.2f}",
        f"+++ R stdev           : {Rstd:,.2f}",
        f"+++ R mean            : {Ravg:,.2f} {get_rmean_qlabel(Ravg)}",
        f"+++ System Quality    : {SysQ:,.2f} {get_system_qlabel(SysQ)}",
        f"+++ R mean (win)      : {pos_mean_r:,.2f}",
        f"+++ R mean (loss)     : {neg_mean_r:,.2f}",
        f"+++ Length mean (win) : {int(pos_mean_len)}",
        f"+++ Length mean (loss): {int(neg_mean_len)}",
        f"+++ Win Rate (%)      : {stats.win_rate:.0f}",
        f"+++ Kelly criterion   : {kelly_criterion:,.2f}",
    ])

    trades_plot(trades_lst, trades_df['Rmul30'].tolist(), stat_str, ctx, stats)

    return stats_df

def generate_summary_report(stat_df, conf_str, quotes_str, ctx):
    ''' generate a pdf report with system summary, configuration and figures'''

    stat_df = stat_df.to_string(index=False)

    fig_a = ctx.path("out/reports/system_trades_plot.png")
    fig_b = ctx.path("out/reports/system_trades_dist_plot.png")
    fig_c = ctx.path("out/reports/balance_plot.png")
    fig_d = ctx.path("out/reports/monte_carlo_sampled_plot.png")
    fig_e = ctx.path("out/plots/URTH_plot.png")

    fig_width = 650

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
            pre {{
                white-space: pre-wrap; /* Preserve whitespace and wrap as needed */
            }}
        </style>
    </head>
    <body>
        <h3>System Configuration</h3>
        <pre style="font-size: 10px;">{conf_str}</pre>
        <h3>Quotes List</h3>
        <pre style="font-size: 14px;">{quotes_str}</pre>
        <h2>System Summary</h2>
        <pre style="font-size: 14px;">{stat_df}</pre>
        
        <img src="file://{fig_a}" style="width:{fig_width}px">
        <img src="file://{fig_b}" style="width:{fig_width}px">
        <img src="file://{fig_c}" style="width:{fig_width}px">
        <img src="file://{fig_d}" style="width:{fig_width}px">
        <img src="file://{fig_e}" style="width:{fig_width}px">
    </body>
    </html>
    """

    HTML(string=html_content).write_pdf(ctx.path("out", "system_summary.pdf"))

def format_to_2_decimals(x):
    # Matches numbers, including negatives and decimals
    if re.match(r"^-?\d+(\.\d+)?$", str(x)):
        return f"{float(x):.2f}"
    return x

def compute_position_size(conf, balance, stats):
    '''return the amount of capital to allocate per trade.'''

    ps = conf["pos_sizing"]

    if ps == "core_equity_risk":
        return balance * conf["risk_percent"] # risk expressed as a % of total equity
    elif ps == "fixed_dollar_risk":
        return conf["risk_amount"]            # total risk per trade in dollars
    elif ps == "fixed_ratio":
        return balance / conf["pos_ratio"]    # position size as ratio of balance
    elif ps == "fixed_amount":
        return conf["pos_amount"]             # position size as a fixed_amount
    elif ps == "kelly":
        return conf['kelly_ratio'] * stats.kelly_crit * balance
    else:
        print(f"The position sizing strategy [{conf['pos_sizing']}] does not exist!")
        sys.exit(1)

def do_balance_simulation(dframe, df_trades_table, conf, last_close_date, ctx, stats):
    ''' simulates the virtual account balance for the trades list '''

    print('+++ Trading simulation (backtest)')

    dframe.sort_values(by='Date', ascending=True, inplace=True)
    dframe.reset_index(drop=True, inplace=True)

    # ensure the 'Date' column is in datetime format
    dframe['Date'] = pd.to_datetime(dframe['Date'], errors='coerce')
    dframe['Date'] = dframe['Date'].dt.strftime('%Y-%m-%d')
    
    # Containers for results
    units_lst: List[float] = []
    gain_lst: List[float] = []
    abs_risk_lst: List[float] = []
    risk_lst: List[float] = []
    invest_lst: List[float] = []
    balance_lst: List[float] = []
    total_balance_lst: List[float] = []
    active_trades: Dict[str, float] = {}  # ticker -> units held

    balance = total_balance = float(conf['balance'])

    ohlc_cache = load_ohlc_cache(dframe['Ticker'].unique(), ctx)

    for row in dframe.itertuples(index=False):

        if row.Enter != '-':
            units, cap_invested = _get_capital_invested(row, conf, balance, stats)
            active_trades[row.Ticker] = units
            units_lst.append(round(units, 2))
            gain_lst.append('-')
            abs_risk_pct = units * row.Risk if balance else 0
            risk_pct = ((units * row.Risk) / balance) * 100 if balance else 0
            abs_risk_lst.append(round(abs_risk_pct, 2))
            risk_lst.append(round(risk_pct, 2))

        if row.Exit != '-':
            units = active_trades[row.Ticker]
            tot_profit = units * round(row.Profit, 2)
            cap_invested = -(units * row.Exit - (units * row.Exit) * float(conf['trading_fee'])/100)
            active_trades[row.Ticker] = 0
            gain_lst.append(round(tot_profit, 2))
            units_lst.append('-')
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

    # average balance and investment before open trade closure
    avg_balance = dframe["Balance"].mean()

    invested_lst = dframe["Invested"].tolist()
    pos_inv_lst = [x for x in invested_lst if x > 0]
    pos_inv_cnt = len(pos_inv_lst)
    avg_invested = sum(pos_inv_lst)/pos_inv_cnt

    # close all open trades to get the total balance
    for key, value in active_trades.items():
        if value != 0:
            tmp_df = df_trades_table.loc[(df_trades_table['Ticker'] == key) & (df_trades_table['LastClose'] != '-'), :]
            closed_ret = float(tmp_df['LastClose']) * float(value)
            balance += closed_ret
            print("Closed: {} {:,.2f}".format(key, closed_ret))
            tmp_row = {
                'Date': last_close_date,
                'Ticker': f"({key})",
                'Enter': tmp_df['PriceIn'].iloc[0],
                'Risk': tmp_df['Risk'].iloc[0],
                'Profit': tmp_df['Profit'].iloc[0],
                'Units': round(float(value), 2),
                'Gain': round(float(tmp_df['Profit'].iloc[0]) * float(value), 2),
                'Exit': float(tmp_df['LastClose']),
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
    
    print(f"\nAverage investment: {avg_invested:,.2f}")
    print(f"Average balance   : {avg_balance:,.2f}")
    print(f"Average risk ($)  : {avg_risk_abs:,.2f}")
    print(f"Average risk (%)  : {avg_risk_per:.2f}")

    # sanity check the sum of the invested colum (start balance + -(invested) = final balance)
    total_invested = dframe['Invested'].sum()
    print(f"\nTotal invested: {total_invested:,.2f}")
    print(f"Final balance : {balance:,.2f}\n")

    if conf['verbose'] == True:
        print('\n', dframe)
    dframe.to_csv(ctx.path("out/tables/", "trades_list.csv"), index=False)

    # save to pdf file
    dframe.index = dframe.index + 1
    dframe['Date'] = pd.to_datetime(dframe['Date'], errors='coerce').dt.strftime('%d-%m-%Y')
    html = df_to_html(dframe)
    HTML(string=html).write_pdf(ctx.path("out", "trades_list.pdf"))

    return dframe

def do_monte_carlo_simulation_sampled(total_trades_list, conf, ctx, stats):
    ''' takes the list of R-multiples and randomly samples from the list (bag of marbles simulation)'''

    # extract Rmul values from the trades list
    Rmul_arr = total_trades_list['Rmul'].dropna().to_numpy()

    # set fixed variables for simulation
    risk = stats.avg_risk / conf['balance'] if len(Rmul_arr) <= conf['sim_len_max'] else (stats.avg_risk/stats.trades_num) * conf['sim_len_max'] / conf['balance']

    run_monte_carlo_sampled(Rmul_arr, conf, ctx, stats, risk)

def run_monte_carlo_sampled(Rmul_arr, conf, ctx, stats, risk):
    ''' run a Monte Carlo balance simulation by sampling from the given R-multiple distribution (bag of marbles) '''

    print(f"+++ Monte Carlo simulation (sampled) ({conf['iterations']} iterations)")

    print(f"+++ Trades total          : {len(Rmul_arr)}")
    print(f"+++ Real Rmul average     : {np.mean(Rmul_arr):.2f}")
    print(f"+++ Real Rmul maximum     : {Rmul_arr.max():.2f}")
    print(f"+++ Real Rmul minimum     : {Rmul_arr.min():.2f}")
    print(f"+++ System Quality Number : {stats.sqn:.2f}")

    # sample from the real distribution as measured by the closed trades
    multiset = Rmul_arr.tolist()
    sample_count = 10000
    Rmul_sample = np.random.choice(multiset, size=sample_count, replace=True)

    print(f"+++ Sampled Rmul average  : {np.mean(Rmul_sample):.2f} (10000 samples)")

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

    # store values for use by later pipeline steps
    stats.max_drawdown = 100.0 - float(min_balance/conf['balance'] * 100)
    stats.min_balance = min_balance

    last_row = mc_result_df.iloc[-1]
    print ("+++ MONTE CARLO results")
    print(f"+++ Median                : {last_row.median():,.0f}")
    print(f"+++ Stdev                 : {last_row.std():,.0f}")
    print(f"+++ Max                   : {last_row.max():,.0f}")
    print(f"+++ Min                   : {last_row.min():,.0f}")
    print(f"+++ Loss streak avg       : {avg_neg_run:.0f}")
    print(f"+++ Loss streak max       : {max_neg_run:.0f}")
    print(f"+++ Minimum balance       : {stats.min_balance:,.0f}")
    print(f"+++ Max drawdown (%)      : {stats.max_drawdown:.1f}")

     # save the balances and plot the result (see simulation plot)
    plot_monte_carlo_results_sampled(mc_result_df, conf, ctx, stats, risk, np.mean(Rmul_arr), np.mean(Rmul_sampled), avg_neg_run, max_neg_run)

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

def ann_return(start_capital: float, end_capital: float, years: float) -> float:
    ''' Compute the annualized rate of return (CAGR) '''
    ratio = end_capital / start_capital
    return ratio ** (1.0 / years) - 1.0

def plot_monte_carlo_results_sampled(mc_result_df, conf, ctx, stats, risk, Rmul_avg, Rmul_avg_sampled, avg_neg_run, max_neg_run):
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
        f"Max drawdown: {stats.max_drawdown:.1f}%\n"
        f"Min balance : ${stats.min_balance:,.0f}\n"
        f"Ravg (sim)  : {Rmul_avg_sampled:.2f}\n"
        f"Ravg (real) : {Rmul_avg:.2f}\n"
        f"SQN         : {stats.sqn:.2f}"
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

    # annualized gain trading simulation (CAGR)
    ann_ret_sim = ann_return(conf['balance'], mc_result_df.iloc[-1].median(), stats.trades_len/365)
    
    y_max = plt.ylim()[1]
    y_val = mc_result_df.iloc[-1].median() + 0.035 * y_max
    plt.text(
        -1.5, y_val, f"${mc_result_df.iloc[-1].median():,.0f} ({ann_ret_sim:.1%})",
        fontsize=10,
        fontfamily='Monospace',
        verticalalignment='top'
    )

    # retrieve the benchmark data (URTH) and compute annualized gain
    val_out = _get_urth_benchmark_result(conf, ctx)
    ann_ret_hodl = ann_return(conf['balance'], val_out, stats.trades_len/365)

    ax.axhline(val_out, color='black', linewidth=1.5, linestyle='-.', alpha=.7)

    y_val = val_out + 0.035 * y_max
    plt.text(
        -1.5, y_val, f"${val_out:,.0f} ({ann_ret_hodl:.1%})",
        fontsize=10,
        fontfamily='Monospace',
        verticalalignment='top'
    )

    ax.set_xlabel('Trade')
    ax.set_ylabel('Balance (USD)')
    ax.grid(True, which='both', linestyle='dotted', alpha=0.5)

    plt.savefig(ctx.path("out/reports", "monte_carlo_sampled_plot.png"), dpi=150)
    plt.close()

def do_monte_carlo_simulation_shuffled(total_trades_list, conf, ctx, stats, last_close_date):
    ''' takes the trades tabel and randomly permutates the trades in the dataframe'''

    print(f"+++ Monte Carlo simulation (shuffled) ({conf['iterations']} iterations)")

    # create new dataframe, keeping only relavant columns
    cols_to_keep = ['Enter','Exit','Ticker','PriceIn', 'PriceOut', 'Profit', 'Risk', 'Rmul','Length']

    # copy values from LastClose into PriceOut (= fill the open trades)
    col_source   = 'LastClose'
    col_target   = 'PriceOut'
    col_target_exit = 'Exit'
    condition    = total_trades_list['LastClose'] != '-'
    monte_carlo_df = total_trades_list[cols_to_keep].copy()
    monte_carlo_df.loc[condition, col_target] = total_trades_list.loc[condition, col_source]
    monte_carlo_df.loc[condition, col_target_exit] = last_close_date

    # add new units and days permutation column
    monte_carlo_df['Units'] = 0.0
    monte_carlo_df['Shift'] = 0

    # rename columns for compatibility
    monte_carlo_df.columns = ['DateIn','DateOut','Ticker','Enter', 'Exit', 'Profit', 'Risk', 'Rmul', 'Length','Units', 'Shift']

    # convert Enter/Exit columns to datetime format
    monte_carlo_df['DateIn'] = pd.to_datetime(monte_carlo_df['DateIn'], format='%d-%m-%Y', errors='coerce')
    monte_carlo_df['DateOut'] = pd.to_datetime(monte_carlo_df['DateOut'], format='%d-%m-%Y', errors='coerce')

    # get first and last day in the dataframe
    start_date = monte_carlo_df['DateIn'].min()
    end_date = monte_carlo_df['DateOut'].max()
    days_delta = (end_date - start_date).days
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    print(f"+++ simulation start: {start_date.date()}")
    print(f"+++ simulation end  : {end_date.date()}")
    print(f"+++ length (days)   : {days_delta}")

    # dataframe to hold the simulation results
    df_results = pd.DataFrame(columns=['balance'])
    
    # transform the dates in the table to days since the start, convert to integer
    tf_monte_carlo_df = _do_date_transform(monte_carlo_df, start_date, end_date, date_range)

    # store columns 'DateIn' and "DateOut' to reuse after shifting dates
    saved_col_dates = tf_monte_carlo_df[['In', 'Out']].copy(deep=True)

    # dataframe to hold balance values of all iterations (for visualisation)
    N = conf['iterations']
    M = days_delta + 1
    mc_result_df = pd.DataFrame(
        data = [[float('nan')] * M for _ in range(N)],
        columns = [f'{i}' for i in range(M)]
    )
    
    np.random.seed(42) 
    for it in range(0, conf['iterations']):

        # restore values of the original dates
        tf_monte_carlo_df[['In', 'Out']] = saved_col_dates[['In', 'Out']]

        # permutate the dataframe (only the trade columns, excluding the dates)
        tf_monte_carlo_df["Shift"] = np.random.randint(0, days_delta, size=len(tf_monte_carlo_df))

        # shift the trade days by shift days        
        tf_monte_carlo_df[['In']] = (tf_monte_carlo_df[['In']].add(tf_monte_carlo_df['Shift'], axis=0))

        # modulo days_delta to loop around on the date range, and if the end date > days_delta
        # then shift the trade back so it ends at the end date 
        tf_monte_carlo_df["In"] = tf_monte_carlo_df["In"] % days_delta
        tf_monte_carlo_df[['Out']] = (tf_monte_carlo_df[['In']].add(tf_monte_carlo_df['Length'], axis=0))

        mask = tf_monte_carlo_df["Out"] > days_delta
        subtract_amount = tf_monte_carlo_df.loc[mask, "Out"] - days_delta
        tf_monte_carlo_df.loc[mask, "In"] -= subtract_amount
        tf_monte_carlo_df.loc[mask, "Out"] = days_delta

        # loop throught the whole datarange, selecting trades on the day it matches
        cap_tot = 0.0
        proceeds_tot = 0.0
        balance = float(conf['balance'])

        for current_day in range(0, days_delta+1):

            # select the rows which match the current enter and exit day
            mask_enter = tf_monte_carlo_df['In'] == current_day
            daily_rows_enter = tf_monte_carlo_df.loc[mask_enter]
            mask_exit = tf_monte_carlo_df['Out'] == current_day
            daily_rows_exit = tf_monte_carlo_df.loc[mask_exit]

            if not daily_rows_enter.empty:

                # shuffle the enter rows found on that day, for better 
                # randomisation (units bought depends on the order)
                rows_as_tuples = list(daily_rows_enter.itertuples(index=False))
                random.shuffle(rows_as_tuples)

                units_list = []
                for row in rows_as_tuples:
                    units, cap_invested = _get_capital_invested(row, conf, balance, stats)
                    balance -= cap_invested
                    units_list.append(units)
                    cap_tot += cap_invested

                tf_monte_carlo_df.loc[daily_rows_enter.index, 'Units'] = units_list

            if not daily_rows_exit.empty:
                for row in daily_rows_exit.itertuples(index=False):
                    proceeds = _get_proceeds(row, conf)
                    balance += proceeds
                    proceeds_tot += proceeds

            # store the balance of day x = current_day (column) at it = idx (row)
            mc_result_df.iat[it, current_day] = balance

        # reset units column
        tf_monte_carlo_df['Units'] = 0.0
        tf_monte_carlo_df['Shift'] = 0

        df_results.loc[len(df_results)] = [balance]
        
        if it % (conf['iterations']/10) == 0:
            # write a dot at every 10% progress
            sys.stdout.write(". ")
            sys.stdout.flush()

    print ("\n+++ MONTE CARLO results")
    print(f"+++ Median          : {df_results['balance'].median():,.0f}")
    print(f"+++ Stdev           : {df_results['balance'].std():,.0f}")
    print(f"+++ Max             : {df_results['balance'].max():,.0f}")
    print(f"+++ Min             : {df_results['balance'].min():,.0f}")
    
    # plot results of the simulation
    plot_monte_carlo_results_shuffled(df_results, mc_result_df, conf, ctx)

    return monte_carlo_df

def plot_monte_carlo_results_shuffled(df_results, mc_result_df, conf, ctx):
    ''' plot the results of the monte carlo simulation '''

    sns.set_style("white")
    fig = plt.figure(figsize = (10, 5))
    fig.suptitle(f"Monte Carlo distribution ({conf['pos_sizing']}) [{conf['iterations']} iterations]", fontsize=16)
    
    # X-axis limit = "outlier-cutoff" * standard deviation of trades distribution
    x_max = df_results['balance'].median() + (conf['outlier'] * df_results['balance'].std())
    plt.xlim(0, x_max)
    
    bins_rice = int(np.ceil(2 * conf['iterations'] ** (1/3)))
    sns.histplot(df_results['balance'], kde=True, bins=bins_rice)

    y_max = plt.ylim()[1]
    x_offset = (plt.xlim()[1] - plt.xlim()[0]) * 0.02

    median_val = df_results['balance'].median()
    annotation_text = f'{median_val:,.0f}'
    plt.annotate(
        annotation_text,
        xy=(median_val, y_max),
        xytext=(median_val + x_offset, y_max * 0.95),
        arrowprops=dict(arrowstyle='-|>', color='brown'),
        ha='left',
        va='top',
        fontsize=12,
        color='brown'
    )

    # retrieve the benchmark data (URTH)
    val_out = _get_urth_benchmark_result(conf, ctx)
    annotation_text = f"HODL {val_out:,.0f}"
    plt.annotate(
        annotation_text,
        xy=(val_out, y_max),
        #xytext=(val_out + x_offset, y_max * 0.95),
        xytext=(val_out - (8 * x_offset), y_max * 0.95),
        arrowprops=dict(arrowstyle='-|>', color='black'),
        ha='left',
        va='top',
        fontsize=12,
        color='black'
    )

    sim_str = (
        f"Min: ${df_results['balance'].min():,.0f}\n"
        f"Max: ${df_results['balance'].max():,.0f}"
        #f"Std: ${df_results['balance'].std():,.0f}"
    )
    plt.text(
        0.03, 0.17, sim_str,
        transform=plt.gca().transAxes,
        fontsize=10,
        fontfamily='Monospace', 
        verticalalignment='top',
        bbox=dict(
            facecolor='white',
            alpha=0.7,
            boxstyle='round,pad=0.5',
            edgecolor='black'
        )
    )

    plt.axvline(conf['balance'], color='green', linestyle='--', label='Balance', linewidth=1, alpha=.7)
    plt.axvline(df_results['balance'].median(), color='brown', label='Median', linestyle='-', linewidth=2, alpha=.7)
    plt.axvline(val_out, color='black', linewidth=2, alpha=.7)
    
    plt.legend(loc='best', fontsize=10)       
    plt.grid(linestyle='--')
    plt.xlabel('Balance (USD)')
    plt.ylabel('Count')

    plt.savefig(ctx.path("out/reports", "monte_carlo_shuffled_result_plot.png"), dpi=150)
    plt.close(fig)

    sns.set_style("white")
    # plot all series of balances for all iterations
    ax = mc_result_df.T.plot(
        figsize=(10, 5),
        color='gray',
        linewidth=0.3,
        marker=None,
        legend=False,
        label='_nolegend_'
    )

    # show a marker for the final balance only
    last_idx = mc_result_df.shape[1] - 1  
    x_last = last_idx
    for row_label, series in mc_result_df.iterrows():
        y_last = series.iloc[-1]
        ax.plot(
            x_last, y_last,
            marker='o',
            markersize=4,
            color='brown',
            alpha=0.3
    )

    # plot min-max values
    sim_str = (
        f"Min: ${df_results['balance'].min():,.0f}\n"
        f"Max: ${df_results['balance'].max():,.0f}"
    )
    ax.text(
        0.03, 0.95, sim_str,
        transform=plt.gca().transAxes,
        fontsize=10,
        fontfamily='Monospace', 
        verticalalignment='top',
        bbox=dict(
            facecolor='white',
            alpha=0.7,
            boxstyle='round,pad=0.5',
            edgecolor='black'
        )
    )

    ax.set_title(f"Monte Carlo results (shuffled) [{conf['iterations']} iterations]", fontsize=16, pad=25)
    ax.axhline(df_results['balance'].median(), color='brown', linestyle='dotted', label='Median', linewidth=1.5, alpha=.7)
    ax.axhline(conf['balance'], color='green', linestyle='--', label='Balance', linewidth=1.5, alpha=.7)
    ax.axhline(val_out, color='black', linewidth=1.5, label='HODL', linestyle='-.', alpha=.7)

    # plot value of median as text
    y_max = plt.ylim()[1]
    y_val = df_results['balance'].median()+ 0.035 * y_max
    plt.text(
        -1.5, y_val, f"${df_results['balance'].median():,.0f}",
        fontsize=10,
        fontfamily='Monospace',
        verticalalignment='top'
    )

    # plot value of HODL as text
    y_val = val_out + + 0.035 * y_max
    plt.text(
        -1.5, y_val, f"${val_out:,.0f}",
        fontsize=10,
        fontfamily='Monospace',
        verticalalignment='top'
    )

    # Y-axis limit = "outlier-cutoff" * standard deviation of trades distribution
    y_max = df_results['balance'].median() + (conf['outlier'] * df_results['balance'].std())
    plt.ylim(0, y_max)

    ax.set_xlabel('Day')
    ax.set_ylabel('Balance (USD)')
    ax.grid(True, which='both', linestyle='--', alpha=0.5)

    plt.savefig(ctx.path("out/reports", "monte_carlo_shuffled_plot.png"), dpi=150)
    plt.close()

def _do_date_transform(df, start, end, range):

    # make a copy of the original df
    tf_df = df.copy()

    # add new integer In and Out columns
    tf_df['In'] = 0
    tf_df['Out'] = 0

    start_date = start
    end_date = end
    date_range = range

    # step through the range and on each day a trade enter 
    # or exit is found mark the days passed since the start
    idx = 0
    for current_day in date_range:
        mask_enter = tf_df['DateIn'].dt.normalize() == current_day
        mask_exit = tf_df['DateOut'].dt.normalize() == current_day
        if mask_enter.any():
            tf_df.loc[mask_enter, 'In'] = idx
        if mask_exit.any():
            tf_df.loc[mask_exit, 'Out'] = idx
        idx += 1

    # drop DateIn and DateOut columns (not needed)
    tf_df = tf_df.drop(columns=['DateIn', 'DateOut'])

    return tf_df

def _get_capital_invested(row, conf, balance, stats):
    ''' return the invested capital and the no. of units bought'''

    # capital allocated for this trade
    capital_per_trade = compute_position_size(conf, balance, stats)

    # number of units for the position sizing strategy
    if conf["pos_sizing"] in {"core_equity_risk", "fixed_dollar_risk"}:
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

    # do not enter trades where the invested amount is too low, and scale down if the investement requires > current balance
    if cap_invested < conf['min_invest']:
        print(f"Investment amount too low, not entering trade! ({row.Ticker})")
        units = 0
        cap_invested = 0
    elif balance < cap_invested:
        print(f"Required balance to low for investment amount, scaling down... ({row.Ticker})")
        units = balance / row.Enter
        fee = units * row.Enter * float(conf["trading_fee"]) / 100
        cap_invested = units * row.Enter - fee
        if units <= 0:
            units = 0
            cap_invested = 0

    return units, cap_invested

def _get_proceeds(row, conf):
    ''' return the proceeds from the trade '''
    return row.Units * row.Exit - (row.Units * row.Exit) * float(conf['trading_fee'])/100

def load_ohlc_cache(tickers, ctx):
    """
    Pre-load each ticker's raw OHLC CSV once, indexed by 'Date', so repeated
    per-row lookups (see get_total_invested_value) don't re-read from disk.
    """
    cache = {}
    for ticker in tickers:
        file_path = ctx.path(f"out/data/{ticker}_ohlc_raw.csv")
        try:
            df = pd.read_csv(file_path)
            cache[ticker] = df.set_index('Date')
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
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

    if conf['verbose'] == True:
        print('\n', dframe)
    dframe.to_csv(ctx.path('out/tables', "trades_table.csv"), index=False)

    # save to pdf file
    dframe.index = dframe.index + 1
    dframe['Enter'] = pd.to_datetime(dframe['Enter'], errors='coerce').dt.strftime('%d-%m-%Y')
    dframe['Exit'] = pd.to_datetime(dframe['Exit'], format='%Y-%m-%d', errors='coerce').dt.strftime('%d-%m-%Y')
    dframe['Exit'] = dframe['Exit'].where(dframe['Exit'].notna(), "-")
    html = df_to_html(dframe)
    HTML(string=html).write_pdf(ctx.path('out', "trades_table.pdf"))

def df_to_html(df,
               font_px: int = 10,
               page_width_mm: int = 297,   # A4 landscape width
               page_height_mm: int = 210,  # A4 landscape height
               margin_mm: int = 10) -> str:    
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

            table {{
                border-collapse: collapse;
                width: 100%;                 /* fill the printable width */
                table-layout: fixed;         /* forces columns to share space */
                word-wrap: break-word;       /* long words break */
                overflow-wrap: anywhere;    /* newer spec – works in WeasyPrint */
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
        </style>
    """    
    html_table = df.to_html(border=0)
    return f"<html><head>{css}</head><body>{html_table}</body></html>"

def _get_urth_benchmark_result(conf, ctx):

    # get benchmarkdata (from MSCI World ETF)
    urth_df = pd.read_csv(ctx.path('out/data', "URTH_ohlc_raw.csv"))
    urth_in = urth_df['Close'].iloc[0]
    urth_out = urth_df['Close'].iloc[-1]
    shares = conf['balance']/urth_in
    return shares * urth_out

def balance_plot(df, conf, ctx):
    ''' plot paper trading simulation results '''

    # retrieve the benchmark data (URTH)
    val_out = _get_urth_benchmark_result(conf, ctx)

    fig = plt.figure(figsize = (10, 5))
    plot_title = f"Trading simulation (backtest) [{conf['pos_sizing']}] (${conf['balance']:,.0f})"
    fig.suptitle(plot_title, fontsize=16)
    
    plt.plot(df.index, df['Balance'],
            color='brown', linewidth=0.7, alpha=0.7,
            label='Balance', linestyle='--')

    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
    plt.plot(df.index, df['Value'],
            color='green', linewidth=2, alpha=0.9,
            label='Value')

    plt.axhline(y=conf['balance'], color='green', linewidth=.9, linestyle='--')

    bal_str = (
        f" HODL: ${val_out:,.0f}\n"
        f"TRADE: ${df.iloc[-1]['Balance']:,.0f}"
    )
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
            edgecolor='black'
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
    plt.savefig(ctx.path("out/reports", "balance_plot.png"), dpi=150)
    plt.close(fig)

def trades_plot(trades_lst, Rmul30_lst, sys_stats, ctx, stats):
    ''' plot trades histograms '''

    trades_tot = len(trades_lst)
    pos_cnt = sum(1 for value in trades_lst if value > 0)
    neg_cnt = sum(1 for value in trades_lst if value < 0)

    Ravg = st.mean(trades_lst)
    #SysQ = (st.mean(trades_lst) / st.stdev(trades_lst)) * math.sqrt(len(trades_lst)) if len(trades_lst) < 100 else (st.mean(trades_lst) / st.stdev(trades_lst)) * math.sqrt(100)
    SysQ = stats.sqn

    xs = np.arange(len(trades_lst))
    fig = plt.figure(figsize = (10, 5))
    fig.suptitle('Trades vs. R-multiple', fontsize=16)
    plt.bar(xs, trades_lst, color='brown', width=0.75)
    plt.plot(xs, Rmul30_lst, color='blue', linewidth=1.5, alpha=.7, linestyle='-', label='Rmul30')
    
    plt.ylabel('R-multiple')
    plt.grid(True, color='grey', linewidth=.5, linestyle='dashed')

    plt.text(
        0.67, 0.97, sys_stats,
        transform=plt.gca().transAxes,
        fontsize=7,
        fontfamily='Monospace', 
        verticalalignment='top',
        bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.5')
    )

    plt.savefig(ctx.path("out/reports", "system_trades_plot.png"), dpi=150)
    plt.close(fig)

    sns.set_style("white")
    fig = plt.figure(figsize = (10, 5))
    fig.suptitle(f"Trades distribution [{trades_tot} trades (+{pos_cnt}:-{neg_cnt})]", fontsize=16)

    df = pd.DataFrame(trades_lst, columns=['Trades'])

    df['Sign'] = df['Trades'].apply(lambda x: 'Positive' if x >= 0 else 'Negative')
    palette = {'Positive': "#22d63a",
               'Negative': "#db1717"}
    
    #ax = sns.histplot(data=df, x="Trades", color='brown', kde=True, alpha=.3, line_kws=dict(linewidth=.7))
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
            edgecolor='black'
        )
    )

    plt.savefig(ctx.path("out/reports", "system_trades_dist_plot.png"), dpi=150)
    plt.close(fig)

def ticker_plot(df, ticker, description, conf, ctx):
    ''' plot ticker + enter and exits points '''

    fig = plt.figure(figsize = (28, 10))
    ax = fig.gca()
    
    # Ensure index is datetime
    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)

    fig.suptitle('{} - {}'.format(description, ticker), fontsize=20)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=conf['date_int']))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m-%Y'))

    plt.text(df.tail(1).index.item(), df.iloc[-1]['Close'], '{:,.2f}'.format(df.iloc[-1]['Close']))
    #plt.text(df.tail(1).index.item(), df.iloc[-1]['CE'], '{:,.2f}'.format(df.iloc[-1]['CE']), alpha=.5)

    plt.plot(df.index, df[['BBu', 'BBl','BBm']], color='black', linewidth=.1)
    plt.fill_between(df.index, df['BBl'], df['BBu'], color='grey', alpha=.05)

    #plt.plot(df.index, df[['DONu', 'DONl','DONm']], color='black', linewidth=.1)
    #plt.fill_between(df.index, df['DONl'], df['DONu'], color='grey', alpha=.05)
    #plt.plot(df.index, df['SMA50'], color='green', linewidth=.5, label='SMA50')

    # SMA 45wk indicator of bear/bull stock market
    plt.plot(df.index, df['SMA225'], color='orange', linewidth=2, linestyle='-.', label='SMA225')
    
    plt.plot(df.index, df['EMA20'], color='green', linewidth=.5, label='EMA20')
    plt.plot(df.index, df['EMA50'], color='brown', linewidth=.5, label='EMA50')
    plt.plot(df.index, df['EMA100'], color='black', linewidth=.5, label='EMA100')
        
    if conf['exit'] == 'CE':
        plt.plot(df.index, df['CE'], color='black', linewidth=.5, linestyle='--', label='CEexit')
    if conf['exit'] == 'CEE':
        plt.plot(df.index, df['CE'], color='black', linewidth=.5, linestyle='--', label='CEexit')
        plt.plot(df.index, df['CE2'], color='brown', linewidth=.5, linestyle='--', label='CE2exit')
        plt.plot(df.index, df['CE15'], color='yellow', linewidth=.5, linestyle='--', label='CE15exit')

    plt.plot(df.index, df['Close'], color='red', linewidth=.8, label='Close')

    if df['Enter'].value_counts().any():
        plt.scatter(df.index, df['Enter'], color='green', label='Enter', marker='^', alpha = 1)
    if df['Exit'].value_counts().any():
        plt.scatter(df.index, df['Exit'], color='darkred', label='Exit', marker='v', alpha = 1)

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
        plt.annotate('R-average: {:,.1f} ({} trades)'.format(df['Rmul'].sum()/df['Rmul'].count(), df['Rmul'].count()), 
                     xy=(0.01, 0), xycoords='axes fraction', fontsize=22, xytext=(0,35), 
                     bbox={'facecolor':'0.9', 'boxstyle':'square', 'alpha':0.2}, textcoords='offset points', ha='left', va='top')

    plt.grid(linestyle='--')
    plt.xlabel('Date')
    plt.ylabel('Price (USD)')
    plt.legend(loc='lower right')
    plt.savefig(ctx.path("out/plots", f"{ticker}_plot.png"), dpi=150)
    plt.close(fig)

def ticker_plot_ta(df, ticker, description, conf, ctx):
    ''' plot ticker +ta indicators + enter and exits points '''

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True, figsize = (28, 15))
    fig.suptitle('{} - {}'.format(description, ticker), fontsize=20)

    # Ensure index is datetime
    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)

    fig.gca().xaxis.set_major_locator(mdates.DayLocator(interval=conf['date_int']))
    fig.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    ax1.text(df.tail(1).index.item(), df.iloc[-1]['Close'], '{:,.2f}'.format(df.iloc[-1]['Close']))
    #ax1.text(df.tail(1).index.item(), df.iloc[-1]['CE'], '{:,.2f}'.format(df.iloc[-1]['CE']), alpha=.5)

    ax1.plot(df.index, df[['BBu', 'BBl','BBm']], color='black', linewidth=.1)
    ax1.fill_between(df.index, df['BBl'], df['BBu'], color='grey', alpha=.05)

    #ax1.plot(df.index, df['SMA50'], color='green', linewidth=.5, label='SMA50')
    #ax1.plot(df.index, df['SMA200'], color='orange', linewidth=.5, label='SMA200')

    ax1.plot(df.index, df['EMA20'], color='green', linewidth=.5, label='EMA20')
    ax1.plot(df.index, df['EMA50'], color='brown', linewidth=.5, label='EMA50')
    ax1.plot(df.index, df['EMA100'], color='black', linewidth=.5, label='EMA100')

    #ax1.plot(df.index, df['CE'], color='black', linewidth=.5, linestyle='--', label='CEexit')
    ax1.plot(df.index, df['Close'], color='red', linewidth=.9, label='Close')

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

    #ax2.plot(df.index, df['RSI'], color='blue', linewidth=.8, label='RSI')
    #ax2.axhline(y=conf['rsi_low'], color='red', linewidth=1, linestyle='-.')
    #ax2.axhline(y=conf['rsi_high'], color='red', linewidth=1, linestyle='-.')
    #ax2.fill_between(df.index, 30, df['RSI'], color='grey', alpha=.1)
    #ax2.set_ylabel('RSI')

    ax2.plot(df.index, df['ADX'], color='blue', linewidth=.8, label='ADX')
    ax2.axhline(y=conf['adx_trend'], color='red', linewidth=1, linestyle='-.')
    ax2.set_ylabel('ADX')

    # Directional Indicators (+DI and -DI)
    #dframe['P_DI']
    #dframe['M_DI'] 

    ax3.plot(df.index, df['P_DI'], color='green', linewidth=.8, label='POS_DI')
    ax3.plot(df.index, df['M_DI'], color='brown', linewidth=.8, label='NEG_DI')

    #ax3.plot(df.index, df['OBV'], color='blue', linewidth=.8, label='OBV')
    #ax3.fill_between(df.index, df['OBV'], 0, color='grey', alpha=.1)
    #ax3.axhline(y=0, color='red', linewidth=1, linestyle='-.')
    #ax3.set_ylabel('OBV')

    #ax3.plot(df.index, df['FI'], color='blue', linewidth=.8, label='FI')
    #ax3.axhline(y=0, color='red', linewidth=1, linestyle='-.')
    #ax3.fill_between(df.index, df['FI'], 0, color='grey', alpha=.1)
    #ax3.set_ylabel('FI')

    if df['Enter'].value_counts().any():
        ax1.scatter(df.index, df['Enter'], color='green', label='Enter', marker='^', alpha = 1)
    if df['Exit'].value_counts().any():
        ax1.scatter(df.index, df['Exit'], color='darkred', label='Exit', marker='v', alpha = 1)

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

    ax1.grid(linestyle='--')
    ax2.grid(linestyle='--')
    ax3.grid(linestyle='--')
    plt.xlabel('Date')
    ax1.set_ylabel('Price(USD)')
    ax1.legend(loc='lower right')
    ax3.legend(loc='lower right')
    plt.savefig(ctx.path("out/plots/TA", f"{ticker}_plot_ta.png"), dpi=150)
    plt.close(fig)
