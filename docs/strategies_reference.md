## Trading Strategies Reference

This page describes the trading strategies you can select in `config/system_conf.json`:
the **enter** strategies (`enter`), the **exit** strategies (`exit`), and the **stoploss**
methods (`stloss`, plus the optional profit-locking ladder). For each one it states what the
strategy is meant to do, then the exact condition under which it fires.

The conditions reference config settings shown in `code font` (e.g. `adx_trend`, `rsi_low`) —
see [system_conf_reference.md](system_conf_reference.md) for what each controls and its allowed
values.

Any enter strategy can be combined with any exit strategy — the engine imposes no restriction.
The natural design is a symmetric pairing (enter on a trend forming, exit on it breaking, using
the same indicator), or a trend/breakout entry handed off to a Chandelier trailing exit
(`CE`/`CEE`/`XR`) to let the move run.

---

### Indicators

The strategy conditions below are built from these technical indicators (all computed in
`add_technical_indicators`, [utils.py](../utils.py)):

- **RSI** — Relative Strength Index. Momentum oscillator bounded 0–100; low = oversold, high = overbought.
- **ATR** — Average True Range. Measures recent volatility (average price range per bar); drives the stoploss distance.
- **ADX** — Average Directional Index. Measures *trend strength* regardless of direction; high ADX = strong trend.
- **+DI / −DI** — Positive/negative Directional Indicators. `+DI > −DI` means up-pressure exceeds down-pressure (and vice-versa).
- **EMA (fast/mid/slow)** — Exponential Moving Averages over increasing periods; react faster than SMAs to recent price.
- **SMA (fast/slow)** — Simple Moving Averages over increasing periods.
- **Bollinger Bands (BBu / BBl)** — Upper/lower volatility bands around a moving average; price at the lower band = stretched down. Fixed at 20 periods, 2σ.
- **Bollinger Breakout Band (BBBu / BBBm)** — A second, separate Bollinger set over `bbb_sma` periods at `bbb_std` standard deviations, used only by the `BBB` strategy. `BBBm` is the middle band, i.e. the SMA over `bbb_sma` periods.
- **Donchian channel (DONup / DONdn)** — Highest high / lowest low over the last N bars; a break of the channel signals a breakout.
- **MACD (MACD / MACDsig / MACDhist)** — Moving Average Convergence Divergence: the MACD line, its signal line, and their histogram.
- **Chandelier Exit (CE / CE2 / CE15)** — A trailing stop set a multiple of the 22-period ATR below the 22-bar high. `CE` is the widest (3×ATR), `CE2` tighter (2×ATR), `CE15` the tightest (1.5×ATR).

---

### Enter strategies (`enter`)

**BBRSI** — *Mean-reversion.* Buys a stretched-down, oversold market betting on a bounce.\
*Fires when:* Close < lower Bollinger band (BBl) **and** RSI < `rsi_low`.\
*Code:* [strategy.py:90](../strategy.py#L90)

**RSI** — *Mean-reversion.* Buys a purely oversold market on RSI alone, without the Bollinger-band confirmation — the mirror of the RSI exit.\
*Fires when:* RSI < `rsi_low`.\
*Code:* [strategy.py:96](../strategy.py#L96)

**3EMA** — *Trend-following.* Buys an established up-trend confirmed by three stacked, rising EMAs.\
*Fires when:* Close > EMAfast > EMAmid > EMAslow, **and** +DI > −DI, **and** ADX > `adx_trend`.\
*Code:* [strategy.py:103](../strategy.py#L103)

**SMA** — *Trend-following.* Same idea as 3EMA but with two simple moving averages.\
*Fires when:* Close > SMAfast > SMAslow, **and** +DI > −DI, **and** ADX > `adx_trend`.\
*Code:* [strategy.py:113](../strategy.py#L113)

**MACD** — *Trend / momentum.* Buys when MACD momentum turns positive inside a confirmed up-trend.\
*Fires when:* MACD > signal line, **and** MACD histogram > 0, **and** +DI > −DI, **and** ADX > `adx_trend`.\
*Code:* [strategy.py:122](../strategy.py#L122)

**DONCH** — *Breakout.* Buys a fresh N-bar high — a pure Donchian channel breakout, no confirmation.\
*Fires when:* Close > upper Donchian channel (DONup).\
*Code:* [strategy.py:131](../strategy.py#L131)

**BBB** — *Bollinger Breakout Band.* Buys a move that stretches above a wide, slow Bollinger upper band — a volatility breakout meant to be held for the long run.\
*Fires when:* Close > upper Bollinger Breakout Band (BBBu).\
*Code:* [strategy.py:138](../strategy.py#L138)

**RAND** — *Random control.* Enters on a random draw, ignoring all indicators. Useful as a baseline: a real edge should beat random entries with the same exit and sizing.\
*Fires when:* a random number in [0,1) is below `rand_level` (e.g. `0.02` ≈ a 2% chance per bar).\
*Code:* [strategy.py:145](../strategy.py#L145)

---

### Exit strategies (`exit`)

The `3EMA`, `SMA` and `MACD` exits mirror their enter counterparts — they fire when the trend
that justified the entry breaks down. `DONCH` exits on the opposite channel break, `BBB` on a
fall back to its own band mean. `RSI` and
`BBRSI` exit on overbought conditions (the mean-reversion counterpart). `TIME` exits purely on
elapsed holding time. `CE`, `CEE` and `XR` are Chandelier trailing stops — the more involved
ones are described with their intent first.

**3EMA** — *Trend breakdown.* Exits when the up-trend inverts into a stacked, falling EMA alignment.\
*Fires when:* Close < EMAfast < EMAmid < EMAslow, **and** −DI > +DI, **and** ADX > `adx_trend`.\
*Code:* [strategy.py:149](../strategy.py#L149)

**SMA** — *Trend breakdown.* The SMA mirror of the 3EMA exit.\
*Fires when:* Close < SMAfast < SMAslow, **and** −DI > +DI, **and** ADX > `adx_trend`.\
*Code:* [strategy.py:159](../strategy.py#L159)

**MACD** — *Momentum breakdown.* Exits when MACD momentum turns negative within a down-turn.\
*Fires when:* MACD < signal line, **and** MACD histogram < 0, **and** −DI > +DI, **and** ADX > `adx_trend`.\
*Code:* [strategy.py:168](../strategy.py#L168)

**DONCH** — *Breakout reversal.* Exits on a fresh M-bar low — the opposite Donchian break to the entry.\
*Fires when:* Close < lower Donchian channel (DONdn).\
*Code:* [strategy.py:183](../strategy.py#L183)

**BBB** — *Breakout give-up.* Holds the breakout until price falls all the way back to the band's own long-term mean.\
*Fires when:* Close < middle Bollinger Breakout Band (BBBm), i.e. the SMA over `bbb_sma` periods.\
*Code:* [strategy.py:190](../strategy.py#L190)

**RSI** — *Overbought.* Exits once momentum reaches an overbought extreme.\
*Fires when:* RSI > `rsi_high`.\
*Code:* [strategy.py:219](../strategy.py#L219)

**BBRSI** — *Overbought mean-reversion.* The exit counterpart to the BBRSI entry — take the bounce once it's stretched up.\
*Fires when:* Close < upper Bollinger band (BBu) **and** RSI > `rsi_high`.\
*Code:* [strategy.py:177](../strategy.py#L177)

**TIME** — *Time-based.* Holds for a fixed number of days, then exits unconditionally — independent of price and of the enter strategy.\
*Fires when:* the trade has been held for `exit_on_day` days (day 1 = the entry day).\
*Code:* [strategy.py:225](../strategy.py#L225)

**CE** — *Chandelier trailing stop.* Rides the trade behind a single trailing stop set a few ATR below the recent high, giving the move room while capping the give-back.\
*Fires when:* the trade is at least `intrade_wait` days old **and** Close < the Chandelier stop (CE).\
*Code:* [strategy.py:213](../strategy.py#L213)

**CEE** — *Progressive Chandelier trailing stop.* A Chandelier trail that tightens as the trade
gets more profitable: losers are cut immediately, young winners are given room, and the stop is
ratcheted progressively tighter the further the trade runs, locking in more of a large gain.
Only active once the trade is at least `intrade_wait` days old. Behaviour by current profit in
R-multiples (`Rcur`):

| Current profit (R) | Behaviour |
| --- | --- |
| ≤ 0 | Exit — cut the loss immediately. |
| 0 – 2 | Hold, even if price dips below the stop — give a young winner room to develop. |
| 2 – 4 | Exit if Close falls below the standard Chandelier stop (CE, widest). |
| 4 – 6 | Exit if Close falls below a tighter stop (CE2). |
| > 6 | Exit if Close falls below the tightest stop (CE15). |

*Code:* [strategy.py:197](../strategy.py#L197)

**XR** — *Chandelier trail with a profit target.* A Chandelier trailing stop combined with a
hard take-profit: it rides the trade behind the stop but also banks the position outright once
a fixed R-multiple target is reached. Only active once the trade is at least `intrade_wait` days old.\
*Fires when:* current profit `Rcur` ≤ 0 (turned into a loss), **or** Close < the Chandelier stop (CE), **or** current profit `Rcur` ≥ `R_profit` (target hit).\
*Code:* [strategy.py:233](../strategy.py#L233)

---

### Stoploss (`stloss`)

The stoploss sets the initial risk level (the "1R" distance) placed below the entry. It is used
both to size the position and, for the moving-average / breakout exits, as the hard stop.

**3atr** — Stop placed 3 × ATR below the close (wide, volatility-scaled).\
*Code:* [strategy.py:39](../strategy.py#L39)

**2atr** — Stop placed 2 × ATR below the close (tighter than `3atr`).\
*Code:* [strategy.py:41](../strategy.py#L41)

**xatr** — Stop placed `atr_factor` × ATR below the close — a custom ATR multiple.\
*Code:* [strategy.py:43](../strategy.py#L43)

**percent** — Stop placed at a fixed fraction of the close (`stoploss`, e.g. `0.95` = 5% below).\
*Code:* [strategy.py:45](../strategy.py#L45)

#### Profit-locking ladder (`stloss_ladder`)

When `stloss_ladder` is enabled, the stop is ratcheted *upward* as the trade runs, locking in
profit at the R-multiple levels configured in `ladder_levels` (a list of `[trigger_R, lock_R]`
pairs: "once the trade's best profit reaches `trigger_R`, move the stop to lock in `lock_R`").
The stop only ever moves up, never down.

The ladder only applies to the **`3EMA`, `SMA`, `MACD`, `DONCH` and `BBB`** exits. The other exits
(`CE`, `CEE`, `XR`, `RSI`, `BBRSI`, `TIME`) manage their own trailing or R-based exits, so the
ladder is ignored for them.

*Code:* [strategy.py:20](../strategy.py#L20)
