# Placeholder for signal generator logic
# src/execution/signal_generator.py
"""
Converts consensus output → actionable trade signal for manual execution.
Generates a complete trade card for the trader.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from .risk_manager import GuardianRiskManager, PositionSizer

console = Console()


class TradeSignal(BaseModel):
    """Complete trade card for manual execution."""
    signal_id: str
    timestamp: str
    
    # Core signal
    direction: str           # LONG | SHORT | NO_TRADE
    instrument: str = "XAUUSD"
    
    # Levels
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    target_1: float
    target_2: Optional[float]
    
    # Size
    lot_size: float
    dollar_risk: float
    risk_pct: float
    
    # Confluence
    consensus_score: float
    agent_alignment: str     # "50/50 Long" etc.
    quality_score: float
    top_rationale: str
    
    # Compliance
    guardian_status: str     # CLEAR | CAUTION | BLOCKED
    warnings: list
    
    # Execution notes
    execution_note: str
    traderspost_payload: Optional[dict] = None


class SignalGenerator:
    """
    Converts simulation output → formatted trade signal.
    """
    
    def __init__(self):
        self.risk_manager = GuardianRiskManager()
    
    def generate_signal(
        self,
        consensus: dict,
        market_snapshot,
        atr: Optional[float] = None
    ) -> TradeSignal:
        """Generate complete trade signal from consensus."""
        
        timestamp = datetime.now().isoformat()
        signal_id = f"BG_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        current_price = market_snapshot.xauusd_price
        atr = atr or market_snapshot.xauusd_atr_14
        
        direction = consensus.get("final_signal", "NO_TRADE")
        
        if direction == "NO_TRADE":
            return self._no_trade_signal(signal_id, timestamp, consensus, market_snapshot)
        
        # Compute entry zone (around current price, refined by consensus)
        entry_buffer = atr * 0.15  # 15% of ATR for zone width
        
        if direction == "LONG":
            # For LONG: buy pullback or breakout
            entry_low = current_price - entry_buffer
            entry_high = current_price + entry_buffer * 0.5
            stop_loss = current_price - (atr * 1.5)   # 1.5 ATR stop
            target_1 = current_price + (atr * 2.0)    # 2 ATR target
            target_2 = current_price + (atr * 3.5)    # 3.5 ATR extended target
        else:  # SHORT
            entry_low = current_price - entry_buffer * 0.5
            entry_high = current_price + entry_buffer
            stop_loss = current_price + (atr * 1.5)
            target_1 = current_price - (atr * 2.0)
            target_2 = current_price - (atr * 3.5)
        
        # Position sizing
        sizing = self.risk_manager.compute_position_size(
            entry_price=(entry_low + entry_high) / 2,
            stop_price=stop_loss,
            direction=direction,
            target_price=target_1
        )
        
        # Compliance check
        risk_state = self.risk_manager.get_risk_state()
        compliance = self.risk_manager.guardian_compliance_check(consensus, risk_state)
        
        # Apply size multiplier from compliance
        adjusted_lots = round(sizing.lot_size * compliance["recommended_size_multiplier"], 2)
        
        # Build execution note
        exec_note = self._build_execution_note(
            direction, entry_low, entry_high, stop_loss, target_1, 
            adjusted_lots, compliance
        )
        
        # TradersPost webhook payload (for semi-automated bridge to MT4/5)
        tp_payload = self._build_traderspost_payload(
            direction, (entry_low + entry_high) / 2,
            stop_loss, target_1, adjusted_lots
        ) if compliance["can_execute"] else None
        
        signal = TradeSignal(
            signal_id=signal_id,
            timestamp=timestamp,
            direction=direction,
            entry_zone_low=round(entry_low, 2),
            entry_zone_high=round(entry_high, 2),
            stop_loss=round(stop_loss, 2),
            target_1=round(target_1, 2),
            target_2=round(target_2, 2) if target_2 else None,
            lot_size=adjusted_lots,
            dollar_risk=sizing.dollar_risk,
            risk_pct=sizing.risk_pct,
            consensus_score=consensus.get("weighted_conviction", 0),
            agent_alignment=(
                f"{consensus['long_votes']}/{consensus['total_active']} Long | "
                f"{consensus['short_votes']}/{consensus['total_active']} Short"
            ),
            quality_score=consensus.get("quality_score", 0),
            top_rationale=consensus.get("top_long_rationale" if direction == "LONG" 
                                       else "top_short_rationale", ["N/A"])[0],
            guardian_status=compliance["compliance_summary"],
            warnings=compliance["warnings"],
            execution_note=exec_note,
            traderspost_payload=tp_payload
        )
        
        self._print_trade_card(signal)
        return signal
    
    def _build_execution_note(
        self, direction, entry_low, entry_high, stop, target, lots, compliance
    ) -> str:
        """Build human-readable execution instructions."""
        action = "BUY" if direction == "LONG" else "SELL"
        return (
            f"MANUAL EXECUTION REQUIRED:\n"
            f"1. Open MT4/5 → XAUUSD chart\n"
            f"2. {action} LIMIT at ${(entry_low + entry_high)/2:,.2f} "
            f"(zone: ${entry_low:,.2f}–${entry_high:,.2f})\n"
            f"3. Set SL at ${stop:,.2f}\n"
            f"4. Set TP at ${target:,.2f}\n"
            f"5. Size: {lots} lots\n"
            f"6. Guardian Status: {compliance['compliance_summary']}\n"
            + ("\n".join(f"   ⚠️ {w}" for w in compliance["warnings"]) if compliance["warnings"] else "")
        )
    
    def _build_traderspost_payload(
        self, direction, entry, stop, target, lots
    ) -> dict:
        """
        TradersPost webhook payload.
        Semi-automated: sends alert to TradersPost → MT4 EA receives it.
        Trader MUST still confirm execution. NOT fully automated.
        """
        return {
            "ticker": "XAUUSD",
            "action": "buy" if direction == "LONG" else "sell",
            "price": entry,
            "quantity": lots,
            "stopLoss": stop,
            "takeProfit": target,
            "message": f"BlueGuardian Signal: {direction} XAUUSD @ {entry}",
            "alert_type": "SEMI_MANUAL_REVIEW_REQUIRED"
        }
    
    def _no_trade_signal(self, signal_id, timestamp, consensus, snapshot) -> TradeSignal:
        return TradeSignal(
            signal_id=signal_id,
            timestamp=timestamp,
            direction="NO_TRADE",
            entry_zone_low=snapshot.xauusd_price,
            entry_zone_high=snapshot.xauusd_price,
            stop_loss=0.0,
            target_1=0.0,
            target_2=None,
            lot_size=0.0,
            dollar_risk=0.0,
            risk_pct=0.0,
            consensus_score=consensus.get("weighted_conviction", 0),
            agent_alignment="NO CONSENSUS",
            quality_score=consensus.get("quality_score", 0),
            top_rationale="; ".join(consensus.get("blocking_reasons", ["No clear setup"])),
            guardian_status="NO TRADE",
            warnings=[],
            execution_note="No qualifying signal today. Patience is a position.",
            traderspost_payload=None
        )
    
    def _print_trade_card(self, signal: TradeSignal):
        """Print formatted trade card to terminal."""
        color = "green" if signal.direction == "LONG" else "red" if signal.direction == "SHORT" else "yellow"
        
        card = (
            f"[bold]Signal ID:[/bold] {signal.signal_id}\n"
            f"[bold]Direction:[/bold] [{color}]{signal.direction}[/{color}]\n"
            f"[bold]Entry Zone:[/bold] ${signal.entry_zone_low:,.2f} – ${signal.entry_zone_high:,.2f}\n"
            f"[bold]Stop Loss:[/bold] ${signal.stop_loss:,.2f}\n"
            f"[bold]Target 1:[/bold] ${signal.target_1:,.2f}\n"
            f"[bold]Target 2:[/bold] ${signal.target_2:,.2f}\n" if signal.target_2 else ""
            f"[bold]Lot Size:[/bold] {signal.lot_size} lots\n"
            f"[bold]Dollar Risk:[/bold] ${signal.dollar_risk:,.2f} ({signal.risk_pct:.1f}%)\n"
            f"[bold]Consensus:[/bold] {signal.consensus_score:.3f} | Quality: {signal.quality_score:.3f}\n"
            f"[bold]Agent Votes:[/bold] {signal.agent_alignment}\n"
            f"[bold]Top Rationale:[/bold] {signal.top_rationale[:100]}\n"
            f"[bold]Guardian Status:[/bold] [{color}]{signal.guardian_status}[/{color}]"
        )
        
        console.print(Panel(card, title="🏅 BLUE GUARDIAN TRADE SIGNAL", 
                          border_style=color, padding=(1, 2)))