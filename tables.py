''' Module defining common dataframes (table) classes '''

import pandas as pd

class TotalTradesList:
    def __init__(self):
        self.df = pd.DataFrame(columns=['Date','Ticker','Enter','Exit','Risk','Profit'])

class TradesTable:
    def __init__(self):
        self.df = pd.DataFrame(columns=['Enter','Exit','Ticker','PriceIn','PriceOut','Risk','Length','Profit','Rmul','MAE','MFE','Rmul30','Signal','LastClose'])
