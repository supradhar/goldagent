# scripts/morning_run.py
"""
BLUE GUARDIAN MORNING ROUTINE
Run this at 5:00 AM PST every trading day.
Full execution: ~15–25 minutes.

MINUTE-BY-MINUTE SCHEDULE:
5:00 AM — Start data pipeline
5:05 AM — Market data fetched, Neo4j updated
5:10 AM — ForexFactory events + Fed speeches ingested
5:15 AM — Knowledge graph context built
5:30 AM — SIMULATION STARTS (all 50+ agents deliberate)
5:50 AM — Consensus computed, trade card generated
5:55 AM — Risk check, compliance validation
6:00 AM — Trade card reviewed by trader (MANUAL REVIEW)
6:05 AM — If approved, TradersPost alert sent
6:10 AM — MT4/5 confirms alert (MANUAL ENTRY)
6:30 AM — Position set before NY open (8:30 AM EST)
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger
from rich.console import Console

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.pipeline import DailyDataPipeline
from src.simulation.parallel_runner import SimulationRunner
from src.execution.signal_generator import SignalGenerator
from src.execution.traderspost_client import TradersPostClient
from src.utils.logger import setup_logger

console = Console()


async def main():
    setup_logger()
    
    console.print(f"""
[bold cyan]
╔══════════════════════════════════════════════════════════════╗
║           BLUE GUARDIAN XAUUSD AI SYSTEM                    ║  
║           Morning Run — {datetime.now().strftime('%Y-%m-%d %H:%M PST')}                  ║
╚══════════════════════════════════════════════════════════════╝
[/bold cyan]""")
    
    # ══════════════════════════════════════════════
    # PHASE 1: DATA INGESTION (5:00–5:15 AM PST)
    # ══════════════════════════════════════════════
    console.print("\n[bold yellow]PHASE 1: DATA INGESTION[/bold yellow]")
    pipeline = DailyDataPipeline()
    pipeline_data = await pipeline.run_full_pipeline()
    
    snapshot = pipeline_data["market_snapshot"]
    kg_context = pipeline_data["kg_context"]
    
    console.print(f"  ✅ Market snapshot: XAUUSD=${snapshot.xauusd_price:,.2f} | "
                  f"DXY={snapshot.dxy_price:.2f} | 10Y={snapshot.us_10y_yield:.2f}%")
    console.print(f"  ✅ Events today: {snapshot.high_impact_events_today} high-impact")
    console.print(f"  ✅ Fed docs: {len(pipeline_data.get('fed_docs', []))} recent speeches")
    
    # Pre-trade checklist
    console.print("\n[bold yellow]PRE-TRADE CHECKLIST:[/bold yellow]")
    checklist = [
        ("High-impact news within 60min?", 
         "⚠️ YES — reduce size" if (snapshot.next_event_in_minutes and snapshot.next_event_in_minutes < 60) 
         else "✅ NO"),
        ("Market open session?", 
         f"✅ {snapshot.xauusd_session}" if snapshot.xauusd_session != "Off_Hours" else "❌ Off Hours"),
        ("Extreme VIX?", 
         "⚠️ HIGH VIX" if snapshot.vix > 30 else "✅ Normal"),
        ("Gold above 200MA?", 
         "✅ YES (structural bull)" if snapshot.xauusd_above_200ma else "⚠️ BELOW 200MA"),
        ("DXY divergence?", 
         "⚠️ DIVERGENCE DETECTED" if snapshot.dollar_gold_divergence else "✅ Normal"),
    ]
    for item, status in checklist:
        console.print(f"  {status} — {item}")
    
    # ══════════════════════════════════════════════
    # PHASE 2: SIMULATION (5:30–5:50 AM PST)
    # ══════════════════════════════════════════════
    console.print("\n[bold yellow]PHASE 2: AGENT SIMULATION[/bold yellow]")
    
    # Wait until 5:30 AM if running early
    # (comment out in testing)
    # await wait_until("05:30")
    
    runner = SimulationRunner(max_workers=int(os.getenv("SIMULATION_WORKERS", "8")))
    simulation_result = await runner.run_simulation(
        market_snapshot=snapshot,
        kg_context=kg_context,
        verbose=True
    )
    
    # Save full simulation output
    output_path = Path(f"data/processed/sim_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(simulation_result, f, indent=2, default=str)
    console.print(f"  ✅ Simulation saved: {output_path}")
    
    # ══════════════════════════════════════════════
    # PHASE 3: SIGNAL GENERATION (5:50–6:00 AM PST)
    # ══════════════════════════════════════════════
    console.print("\n[bold yellow]PHASE 3: SIGNAL GENERATION[/bold yellow]")
    
    consensus = simulation_result["consensus"]
    signal_gen = SignalGenerator()
    trade_signal = signal_gen.generate_signal(consensus, snapshot)
    
    # ══════════════════════════════════════════════
    # PHASE 4: MANUAL REVIEW (6:00–6:10 AM PST)
    # ══════════════════════════════════════════════
    console.print("\n[bold yellow]PHASE 4: MANUAL REVIEW[/bold yellow]")
    
    if trade_signal.direction == "NO_TRADE":
        console.print("  [dim]No signal today. Session complete.[/dim]")
        return
    
    if trade_signal.guardian_status == "BLOCKED":
        console.print(f"  [red]SIGNAL BLOCKED by compliance check.[/red]")
        for block in trade_signal.warnings:
            console.print(f"    {block}")
        return
    
    # Display execution instructions
    console.print(f"\n  [bold]EXECUTION INSTRUCTIONS:[/bold]")
    console.print(f"  {trade_signal.execution_note}")
    
    # Ask for trader confirmation (semi-manual compliance)
    console.print("\n  [bold cyan]AWAITING TRADER CONFIRMATION...[/bold cyan]")
    console.print("  Type 'EXECUTE' to send TradersPost alert (then manually confirm in MT4)")
    console.print("  Type 'SKIP' to pass on today's signal")
    console.print("  Type 'HALF' to execute at 50% size")
    
    user_input = input("  > ").strip().upper()
    
    if user_input in ("EXECUTE", "HALF"):
        if user_input == "HALF":
            trade_signal.lot_size = round(trade_signal.lot_size * 0.5, 2)
            trade_signal.dollar_risk = round(trade_signal.dollar_risk * 0.5, 2)
        
        tp_client = TradersPostClient()
        if trade_signal.traderspost_payload:
            trade_signal.traderspost_payload["quantity"] = trade_signal.lot_size
            success = await tp_client.send_alert(trade_signal.traderspost_payload)
            if success:
                console.print("  [green]✅ Alert sent to TradersPost[/green]")
                console.print("  [yellow]⚡ Confirm manually in MT4/5 before NY open[/yellow]")
        
        # Log trade
        trade_log = {
            "signal_id": trade_signal.signal_id,
            "timestamp": trade_signal.timestamp,
            "direction": trade_signal.direction,
            "lots": trade_signal.lot_size,
            "entry": (trade_signal.entry_zone_low + trade_signal.entry_zone_high) / 2,
            "stop": trade_signal.stop_loss,
            "target": trade_signal.target_1,
            "consensus_score": trade_signal.consensus_score,
            "quality_score": trade_signal.quality_score,
            "trader_confirmed": True
        }
        with open("data/processed/trade_log.jsonl", "a") as f:
            f.write(json.dumps(trade_log) + "\n")
    
    elif user_input == "SKIP":
        console.print("  [dim]Signal skipped by trader.[/dim]")
    
    console.print(f"\n[bold green]✅ Morning routine complete.[/bold green]")
    console.print(f"  Next run: tomorrow 5:00 AM PST")


if __name__ == "__main__":
    asyncio.run(main())