''' Module defining trading strategy classes '''

import sys
import random
import logging

logger = logging.getLogger(__name__)

class Stoploss():
    ''' STOPLOSS strategy '''
    def __init__(self, conf):
        self.conf = conf

    def get_stoploss(self, row):
        if self.conf['stloss'] == '3atr':
            return self._ATRStoploss(row, 3)
        elif self.conf['stloss'] == '2atr':
            return self._ATRStoploss(row, 2)
        elif self.conf['stloss'] == 'xatr':
            return self._ATRStoploss(row, float(self.conf['atr_factor']))
        elif self.conf['stloss'] == 'percent':
            return self._PercentageStoploss(row)
        else:
            logger.critical("The Stoploss strategy {} does not exist!".format(self.conf['stloss']))
            sys.exit(1)

    def _ATRStoploss(self, row, mult):
        return row['Close'] - mult * row['ATR']

    def _PercentageStoploss(self, row,):
        return row['Close'] * float(self.conf['stoploss'])

class TradingSignals(object):
    ''' ENTER and EXIT signals strategy '''

    enter_str = {"BBRSI": "_BB_RSI_Enter",
                 "3EMA":  "_3_EMA_Enter",
                 "SMA": "_SMA_Enter",
                 "MACD": "_MACD_Enter",
                 "DONCH": "_DONCH_Enter"}

    exit_str  = {"CE": "_CE_Exit",
                 "CEE": "_CEE_Exit",
                 "RSI": "_RSI_Exit",
                 "XR": "_XR_Exit",
                 "3EMA": "_3_EMA_Exit",
                 "SMA": "_SMA_Exit",
                 "MACD": "_MACD_Exit",
                 "BBRSI": "_BB_RSI_Exit",
                 "DONCH": "_DONCH_Exit"}

    def __init__(self, conf):
        self.conf = conf

    def check_enter_signal(self, row):
        return getattr(TradingSignals, self.enter_str[self.conf['enter']])(self, row)

    def check_exit_signal(self, row, intrade):
        return getattr(TradingSignals, self.exit_str[self.conf['exit']])(self, row, intrade)
    
    def _BB_RSI_Enter(self, row):
        signal = False
        if row['Close'] < row['BBl'] and row['RSI'] < float(self.conf['rsi_low']):
            signal = True
        return signal

    def _3_EMA_Enter(self, row):
        signal = False
        if row['Close'] > row['EMA20']  and  \
           row['EMA20'] > row['EMA50']  and  \
           row['EMA50'] > row['EMA100'] and  \
           row['P_DI']  > row['M_DI']   and  \
           row['ADX']   > float(self.conf['adx_trend']):
            signal = True
        return signal

    def _SMA_Enter(self, row):
        signal = False
        if row['Close'] > row['SMAfast']   and  \
           row['SMAfast'] > row['SMAslow'] and  \
           row['P_DI']  > row['M_DI']      and  \
           row['ADX']   > float(self.conf['adx_trend']):
            signal = True
        return signal
    
    def _MACD_Enter(self, row):
        signal = False
        if row['MACD'] > row['MACDsig'] and \
           row['MACDhist'] > 0.0        and \
           row['P_DI']  > row['M_DI']   and \
           row['ADX']   > float(self.conf['adx_trend']):
            signal = True
        return signal

    def _DONCH_Enter(self, row):
        # pure Donchian breakout: Close above the prior-N-day high channel
        signal = False
        if row['Close'] > row['DONup']:
            signal = True
        return signal

    def _3_EMA_Exit(self, row, intrade):
        signal = False
        if row['Close'] < row['EMA20']  and \
           row['EMA20'] < row['EMA50']  and \
           row['EMA50'] < row['EMA100'] and \
           row['M_DI']  > row['P_DI']   and \
           row['ADX']   > float(self.conf['adx_trend']):
            signal = True
        return signal

    def _SMA_Exit(self, row, intrade):
        signal = False
        if row['Close'] < row['SMAfast']   and \
           row['SMAfast'] < row['SMAslow'] and \
           row['M_DI']  > row['P_DI']      and \
           row['ADX']   > float(self.conf['adx_trend']):
            signal = True
        return signal

    def _MACD_Exit(self, row, intrade):
        signal = False
        if row['MACD'] < row['MACDsig'] and \
           row['MACDhist'] < 0.0        and \
           row['M_DI']  > row['P_DI']   and \
           row['ADX']   > float(self.conf['adx_trend']):
            signal = True
        return signal

    def _BB_RSI_Exit(self, row, intrade):
        signal = False
        if row['Close'] < row['BBu'] and row['RSI'] > float(self.conf['rsi_high']):
            signal = True
        return signal

    def _DONCH_Exit(self, row, intrade):
        # pure Donchian breakout: Close below the prior-M-day low channel
        signal = False
        if row['Close'] < row['DONdn']:
             signal = True
        return signal

    def _CEE_Exit(self, row, intrade):
        signal = False
        if intrade >= float(self.conf['intrade_wait']):
            if row['Rcur'] <= 0:
                signal = True
            elif row['Rcur'] > 0 and row['Rcur'] < 2 and row['Close'] < row['CE']:
                # stay in the position
                pass
            elif row['Rcur'] > 6 and row['Close'] < row['CE15']:
                signal = True
            elif row['Rcur'] > 4 and row['Close'] < row['CE2']:
                signal = True
            elif row['Close'] < row['CE']:
                signal = True
        return signal

    def _CE_Exit(self, row, intrade):
        signal = False
        if intrade >= float(self.conf['intrade_wait']) and row['Close'] < row['CE']:
            signal = True
        return signal

    def _RSI_Exit(self, row, intrade):
        signal = False
        if row['RSI'] > float(self.conf['rsi_high']):
            signal = True
        return signal

    def _XR_Exit(self, row, intrade):
        signal = False
        if intrade >= float(self.conf['intrade_wait']):
            if row['Rcur'] <= 0 or row['Close'] < row['CE']:
                signal = True
            elif row['Rcur'] >= self.conf['R_profit']:
                signal = True
        return signal
