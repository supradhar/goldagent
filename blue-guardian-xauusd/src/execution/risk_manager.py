# Placeholder for risk manager logic
# src/execution/risk_manager.py
"""
Blue Guardian compliance risk manager.
HARD RULES: 
- Max 4% daily drawdown (Guardian hard limit)
- Guardian Shield: alert at 0.8% drawdown (soft stop)
- Max 1% risk per trade
- No automated order execution (semi-manual only)
"""
import os
from datetime import datetime, date
from typing import Optional, Dict
from pydantic import BaseModel
from loguru import logger


class RiskState(BaseModel):
    """Current state of risk exposure."""
    date: str
    account_balance: float
    starting_balance_today: float
    current_balance: float
    daily_pnl: float
    daily_pnl_pct: float
    daily_drawdown_pct: float         # From day's high
    max_daily_drawdown_limit: float   # 4.0%
    soft_stop_drawdown_pct: float     # 0.8%
    soft_stop_triggered: bool
    hard_stop_triggered: bool
    trades_today: int
    max_trades_per_day: int           # 3 for Blue Guardian
    can_take_new_trade: bool
    open_positions: int
    current_risk_exposure_pct: float


class PositionSizer(BaseModel):
    """Output of position sizing calculation."""
    entry_price: float
    stop_price: float
    account_balance: float
    risk_pct: float                   # e.g., 0.01 = 1%
    dollar_risk: float
    stop_distance_usd: float          # per oz
    lot_size: float                   # in mini lots (0.1 = 10 oz)
    standard_lots: float              # for MT4/5 display
    approximate_margin: float
    risk_reward_ratio: Optional[float]
    target_price: Optional[float]
    dollar_profit_target: Optional[float]
    notes: str


class GuardianRiskManager:
    """
    Blue Guardian 1-Step Challenge compliance module.
    
    Challenge Rules (encoded):
    - Profit Target: 8-10% ($4,000-$5,000 on $50K account)
    - Max Daily Drawdown: 4% ($2,000)
    - Max Overall Drawdown: 8% ($4,000)
    - Min Trading Days: 5
    - Max Risk Per Trade: 1% (our conservative rule, challenge may allow more)
    - No HFT, no tick scalping, no automation of order entry
    """
    
    def __init__(self):
        self.account_balance = float(os.getenv("ACCOUNT_BALANCE", "50000"))
        self.max_daily_risk_pct = float(os.getenv("MAX_DAILY_RISK_PCT", "0.04"))  # 4%
        self.risk_per_trade_pct = float(os.getenv("RISK_PER_TRADE_PCT", "0.01"))  # 1%
        self.soft_stop_pct = float(os.getenv("SOFT_STOP_PCT", "0.008"))           # 0.8%
        
        # Daily state (reset each day)
        self.day_start_balance = self.account_balance
        self.day_high_balance = self.account_balance
        self.current_balance = self.account_balance
        self.trades_today = 0
        self.max_trades_per_day = 3  # Conservative Blue Guardian limit
        self.current_date = date.today().isoformat()
    
    def update_balance(self, new_balance: float):
        """Update current balance after trade close or mark-to-market."""
        if date.today().isoformat() != self.current_date:
            self._reset_daily_state(new_balance)
        
        self.current_balance = new_balance
        self.day_high_balance = max(self.day_high_balance, new_balance)
        logger.info(f"Balance updated: ${new_balance:,.2f} | "
                   f"Daily P&L: ${new_balance - self.day_start_balance:+,.2f}")
    
    def _reset_daily_state(self, balance: float):
        """Reset daily counters at start of new trading day."""
        self.current_date = date.today().isoformat()
        self.day_start_balance = balance
        self.day_high_balance = balance
        self.current_balance = balance
        self.trades_today = 0
        logger.info(f"Daily state reset | Starting balance: ${balance:,.2f}")
    
    def get_risk_state(self) -> RiskState:
        """Get current risk exposure state."""
        daily_pnl = self.current_balance - self.day_start_balance
        daily_pnl_pct = daily_pnl / self.day_start_balance
        
        # Drawdown from day's high
        drawdown_from_high = (self.day_high_balance - self.current_balance) / self.day_high_balance
        
        soft_stop = drawdown_from_high >= self.soft_stop_pct
        hard_stop = drawdown_from_high >= self.max_daily_risk_pct
        
        can_trade = (
            not hard_stop and
            self.trades_today < self.max_trades_per_day
        )
        
        return RiskState(
            date=self.current_date,
            account_balance=self.account_balance,
            starting_balance_today=self.day_start_balance,
            current_balance=self.current_balance,
            daily_pnl=round(daily_pnl, 2),
            daily_pnl_pct=round(daily_pnl_pct * 100, 3),
            daily_drawdown_pct=round(drawdown_from_high * 100, 3),
            max_daily_drawdown_limit=self.max_daily_risk_pct * 100,
            soft_stop_drawdown_pct=self.soft_stop_pct * 100,
            soft_stop_triggered=soft_stop,
            hard_stop_triggered=hard_stop,
            trades_today=self.trades_today,
            max_trades_per_day=self.max_trades_per_day,
            can_take_new_trade=can_trade,
            open_positions=0,  # integrate with broker API
            current_risk_exposure_pct=0.0
        )
    
    def compute_position_size(
        self,
        entry_price: float,
        stop_price: float,
        direction: str,
        target_price: Optional[float] = None,
        risk_override_pct: Optional[float] = None
    ) -> PositionSizer:
        """
        Compute exact position size for Blue Guardian trade.
        
        Gold spec: 1 standard lot = 100 oz
                   1 mini lot   = 10 oz
                   1 micro lot  = 1 oz
        P&L: each $1 move in gold = $100 per standard lot
        """
        risk_state = self.get_risk_state()
        
        if not risk_state.can_take_new_trade:
            logger.warning(
                f"Cannot take new trade: "
                f"{'Hard stop triggered' if risk_state.hard_stop_triggered else ''}"
                f"{'Max trades reached' if risk_state.trades_today >= self.max_trades_per_day else ''}"
            )
        
        # Risk amount in dollars
        risk_pct = risk_override_pct or self.risk_per_trade_pct
        dollar_risk = self.current_balance * risk_pct
        
        # Stop distance
        stop_distance = abs(entry_price - stop_price)
        
        if stop_distance < 0.50:
            notes = "⚠️ STOP TOO TIGHT (< $0.50) — minimum $2 stop recommended for gold"
            stop_distance = 2.0  # Minimum safety stop distance
        elif stop_distance > entry_price * 0.02:
            notes = "⚠️ STOP VERY WIDE (> 2%) — consider reducing position size"
        else:
            notes = "✅ Stop distance within normal range"
        
        # Validate direction
        if direction == "LONG" and stop_price >= entry_price:
            notes += " | ❌ INVALID: Long stop must be BELOW entry"
            stop_price = entry_price * 0.995
            stop_distance = abs(entry_price - stop_price)
        elif direction == "SHORT" and stop_price <= entry_price:
            notes += " | ❌ INVALID: Short stop must be ABOVE entry"
            stop_price = entry_price * 1.005
            stop_distance = abs(entry_price - stop_price)
        
        # Position size in oz
        oz_size = dollar_risk / stop_distance
        
        # Convert to lots (1 standard lot = 100 oz)
        standard_lots = oz_size / 100
        mini_lots = oz_size / 10
        
        # Round down to nearest 0.01 lot (10 oz) for broker
        standard_lots_rounded = max(0.01, round(standard_lots, 2))
        actual_oz = standard_lots_rounded * 100
        actual_dollar_risk = actual_oz * stop_distance
        
        # Approximate margin (at 1:100 leverage, typical retail broker)
        approximate_margin = (entry_price * actual_oz) / 100
        
        # Risk:Reward
        rr = None
        profit_target = None
        if target_price:
            profit_distance = abs(target_price - entry_price)
            rr = profit_distance / stop_distance
            profit_target = actual_oz * profit_distance
        
        # Soft stop check
        if actual_dollar_risk > dollar_risk * 1.05:
            notes += f" | ⚠️ Actual risk ${actual_dollar_risk:.0f} slightly exceeds target ${dollar_risk:.0f}"
        
        result = PositionSizer(
            entry_price=entry_price,
            stop_price=stop_price,
            account_balance=self.current_balance,
            risk_pct=risk_pct * 100,
            dollar_risk=round(dollar_risk, 2),
            stop_distance_usd=round(stop_distance, 2),
            lot_size=round(standard_lots_rounded, 2),
            standard_lots=round(standard_lots_rounded, 2),
            approximate_margin=round(approximate_margin, 2),
            risk_reward_ratio=round(rr, 2) if rr else None,
            target_price=target_price,
            dollar_profit_target=round(profit_target, 2) if profit_target else None,
            notes=notes
        )
        
        logger.info(
            f"\n{'='*55}\n"
            f"  POSITION SIZE CALCULATION\n"
            f"  Direction:     {direction}\n"
            f"  Entry:         ${entry_price:,.2f}\n"
            f"  Stop:          ${stop_price:,.2f}\n"
            f"  Stop Distance: ${stop_distance:.2f}\n"
            f"  Dollar Risk:   ${actual_dollar_risk:,.2f} "
            f"({risk_pct*100:.1f}% of ${self.current_balance:,.0f})\n"
            f"  Size:          {standard_lots_rounded:.2f} lots ({actual_oz:.0f} oz)\n"
            f"  Est. Margin:   ${approximate_margin:,.2f}\n"
            f"  R:R Ratio:     {rr:.2f}:1\n" if rr else ""
            f"  Target:        ${target_price:,.2f} "
            f"(+${profit_target:,.2f})\n" if target_price else ""
            f"  {notes}\n"
            f"{'='*55}"
        )
        
        return result
    
    def guardian_compliance_check(self, consensus: dict, risk_state: RiskState) -> dict:
        """
        Final compliance check before presenting signal for manual execution.
        Returns actionable signal or block with reason.
        """
        blocks = []
        warnings = []
        
        # Hard blocks
        if risk_state.hard_stop_triggered:
            blocks.append(f"🚫 DAILY DRAWDOWN LIMIT HIT ({risk_state.daily_drawdown_pct:.2f}% of {risk_state.max_daily_drawdown_limit:.1f}% limit)")
        
        if risk_state.trades_today >= risk_state.max_trades_per_day:
            blocks.append(f"🚫 MAX TRADES TODAY REACHED ({risk_state.trades_today}/{risk_state.max_trades_per_day})")
        
        if consensus.get("final_signal") == "NO_TRADE":
            blocks.append("🚫 NO CONSENSUS SIGNAL (below 80% threshold)")
        
        # Soft warnings
        if risk_state.soft_stop_triggered:
            warnings.append(f"⚠️ GUARDIAN SHIELD: Drawdown {risk_state.daily_drawdown_pct:.2f}% ≥ 0.8% soft limit — reduce size or pause")
        
        if consensus.get("quality_score", 0) < 0.6:
            warnings.append(f"⚠️ LOW QUALITY SCORE ({consensus.get('quality_score', 0):.2f}) — consider skipping")
        
        if consensus.get("risk_adjusted_conviction", 0) < 0.55:
            warnings.append(f"⚠️ LOW CONVICTION ({consensus.get('risk_adjusted_conviction', 0):.2f}) — half position recommended")
        
        can_execute = len(blocks) == 0
        
        return {
            "can_execute": can_execute,
            "blocks": blocks,
            "warnings": warnings,
            "recommended_size_multiplier": 0.5 if risk_state.soft_stop_triggered else 1.0,
            "compliance_summary": "CLEAR" if can_execute and not warnings else 
                                   "PROCEED WITH CAUTION" if can_execute else "BLOCKED"
        }