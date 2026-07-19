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
    # longest win/loss streaks over the actual realised trade sequence (set by generate_system_stats)
    real_max_win_streak: int = 0
    real_max_loss_streak: int = 0
    avg_risk: float = 0.0
    min_balance: float = 0.0
    max_drawdown: float = 0.0
    # Monte Carlo results (set by run_monte_carlo_sampled)
    avg_loss_streak: float = 0.0
    max_loss_streak: int = 0
    rmul_avg_sampled: float = 0.0
    sqn_sampled: float = 0.0
    min_end_balance: float = 0.0
    # balance-simulation results, consumed by the summary report's balance table
    open_trades_closed: int = 0
    avg_invested: float = 0.0
    avg_balance: float = 0.0
    avg_value: float = 0.0
    avg_risk_per: float = 0.0
    final_balance: float = 0.0
    cagr: float = 0.0
    # daily equity-curve results (set by do_equity_simulation)
    best_month: float = 0.0
    worst_month: float = 0.0
    avg_month: float = 0.0
    best_rolling_cagr: float = 0.0
    worst_rolling_cagr: float = 0.0
    max_dd_recovery: int = 0
    max_dd_recovery_from: str = "-"
    max_dd_recovery_to: str = "-"
