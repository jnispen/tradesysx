''' Shared run context and pipeline statistics, passed explicitly between modules '''

import os
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RunContext:
    ''' run-level settings: base directory, telegram credentials, benchmark dataframe
        and the EUR/USD rate used for the charts' secondary price label '''
    basedir: str
    bot_token: str = ""
    chat_id: str = ""
    outdir: str = "out"
    benchmark_df: Any = None
    # USD per EUR (EURUSD=X close), set when conf['price_eur'] is on; the price
    # charts print the last close in EUR next to the USD value when it is set
    eurusd: Optional[float] = None
    # currency each ticker is quoted in, per yfinance's .info (filled alongside
    # eurusd) - a ticker not quoted in USD is never converted
    currency: dict = field(default_factory=dict)
    # traded tickers grouped by the currency they are quoted in, {currency:
    # [tickers]}, and whether that is more than one currency. Set by
    # utils.check_currency_mix; a mixed list makes every step that adds trades
    # up into one account balance meaningless, so those are skipped
    currency_groups: dict = field(default_factory=dict)
    mixed_currency: bool = False

    def price_label(self, ticker):
        """Y-axis label for a ticker's price panel, naming the currency it is quoted in.

        Falls back to USD when the currency isn't known (lookup failed, or the
        chart was produced outside the pipeline), which is what the charts
        assumed before the currency was looked up at all.
        """
        return 'Price ({})'.format(self.currency.get(ticker) or 'USD')

    def eur_rate(self, ticker):
        """EUR/USD rate to use for a ticker's price label, None when it doesn't apply.

        Only tickers confirmed to be quoted in USD are converted: an unknown
        currency (lookup failed) or a non-USD one leaves the chart unconverted
        rather than printing a wrong EUR value.
        """
        if not self.eurusd:
            return None
        currency = self.currency.get(ticker) or ''
        return self.eurusd if currency.upper() == 'USD' else None

    def currency_summary(self):
        """The traded tickers per currency, e.g. "EUR (ASML.AS, MC.PA), USD (AAPL)"."""
        return ', '.join(f"{currency} ({', '.join(tickers)})"
                         for currency, tickers in sorted(self.currency_groups.items()))

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
    # end-of-run portfolio snapshot, taken before the balance simulation closes
    # its open trades out - the only point where cash, units and mark-to-market
    # values all hold at once. Consumed by the portfolio composition figure.
    portfolio_cash: float = 0.0
    portfolio_positions: list = field(default_factory=list)
    # daily equity-curve results (set by do_equity_simulation)
    best_month: float = 0.0
    worst_month: float = 0.0
    avg_month: float = 0.0
    std_month: float = 0.0
    avg_month_pct: float = 0.0
    std_month_pct: float = 0.0
    best_trailing_1y: float = 0.0
    worst_trailing_1y: float = 0.0
    avg_trailing_1y: float = 0.0
    max_dd_recovery: int = 0
    max_dd_recovery_from: str = "-"
    max_dd_recovery_to: str = "-"
    # real max drawdown (%) of the daily equity curve, and the ratios derived
    # from it and from stats.cagr - None when the denominator is 0/undefined
    max_drawdown_pct: float = 0.0
    sharpe_ratio: Optional[float] = None
    mar_ratio: Optional[float] = None
