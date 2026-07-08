''' Shared run context and pipeline statistics, passed explicitly between modules '''

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class RunContext:
    ''' run-level settings: base directory, telegram credentials and benchmark dataframe '''
    basedir: str
    bot_token: str = ""
    chat_id: str = ""
    outdir: str = "out"
    benchmark_df: Any = None

    def path(self, *parts):
        """Return a string path inside basedir."""
        p = os.path.join(self.basedir, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def outpath(self, *parts):
        """Return a string path inside the configured output directory."""
        return self.path(self.outdir, *parts)


@dataclass
class SystemStats:
    ''' statistics computed during the pipeline and consumed by later steps '''
    sqn: float = 0.0
    kelly_crit: float = 0.0
    trades_len: int = 0
    trades_num: int = 0
    win_rate: float = 0.0
    avg_risk: float = 0.0
    min_balance: float = 0.0
    max_drawdown: float = 0.0
    # balance-simulation results, consumed by the summary report's balance table
    open_trades_closed: int = 0
    avg_invested: float = 0.0
    avg_balance: float = 0.0
    avg_risk_per: float = 0.0
    final_balance: float = 0.0
    cagr: float = 0.0
