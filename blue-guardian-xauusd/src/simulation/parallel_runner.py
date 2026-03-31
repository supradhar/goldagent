# Placeholder for parallel simulation runner
# src/simulation/parallel_runner.py
"""
Runs all agents in parallel, collects votes, computes consensus.
Target: 50-100 agents completed in < 3 minutes.
"""
import asyncio
import time
from typing import List, Tuple
from datetime import datetime
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table
from ..agents.agent_registry import AgentRegistry
from ..agents.base_agent import AgentVote
from .consensus import ConsensusEngine
from .market_state import MarketSnapshot

console = Console()


class SimulationRunner:
    """
    Runs the daily morning simulation.
    
    Execution strategy:
    - Batch agents into groups of SIMULATION_WORKERS (default: 8)
    - Each batch runs fully async
    - Collect all votes, compute consensus
    - Total time: ~2-4 minutes for 50 agents (Claude API)
                  ~8-15 minutes for 50 agents (local Ollama 70B)
    """
    
    def __init__(self, max_workers: int = 8):
        self.registry = AgentRegistry()
        self.consensus_engine = ConsensusEngine()
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
    
    async def run_simulation(
        self,
        market_snapshot: MarketSnapshot,
        kg_context: str,
        verbose: bool = True
    ) -> dict:
        """
        Main simulation entry point.
        Returns full consensus report with all agent votes.
        """
        start_time = time.time()
        agents = self.registry.get_all_agents()
        
        if verbose:
            console.print(f"\n[bold cyan]🎯 BLUE GUARDIAN SIMULATION[/bold cyan]")
            console.print(f"[dim]Running {len(agents)} agents | "
                         f"XAUUSD: ${market_snapshot.xauusd_price:,.2f} | "
                         f"{datetime.now().strftime('%Y-%m-%d %H:%M PST')}[/dim]\n")
        
        # Run all agents with semaphore control
        votes = await self._run_all_agents(agents, market_snapshot, kg_context, verbose)
        
        # Compute consensus
        consensus = self.consensus_engine.compute_consensus(votes, market_snapshot)
        
        elapsed = time.time() - start_time
        
        if verbose:
            self._print_results(votes, consensus, elapsed)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "market_snapshot": market_snapshot.dict(),
            "votes": [v.dict() for v in votes],
            "consensus": consensus,
            "total_agents": len(votes),
            "elapsed_seconds": round(elapsed, 1)
        }
    
    async def _run_all_agents(
        self,
        agents,
        snapshot: MarketSnapshot,
        kg_context: str,
        verbose: bool
    ) -> List[AgentVote]:
        """Run all agents with rate limiting."""
        
        async def run_with_semaphore(agent) -> AgentVote:
            async with self.semaphore:
                try:
                    vote = await asyncio.wait_for(
                        agent.deliberate(snapshot, kg_context),
                        timeout=45  # 45 second timeout per agent
                    )
                    if verbose:
                        emoji = "🟢" if vote.direction == "LONG" else \
                                "🔴" if vote.direction == "SHORT" else "⚪"
                        logger.debug(
                            f"  {emoji} {agent.name[:35]:<35} "
                            f"{vote.direction:<7} "
                            f"conv={vote.conviction:.2f}"
                        )
                    return vote
                except asyncio.TimeoutError:
                    logger.warning(f"Agent {agent.name} timed out")
                    return agent._fallback_vote()
                except Exception as e:
                    logger.error(f"Agent {agent.name} error: {e}")
                    return agent._fallback_vote()
        
        tasks = [run_with_semaphore(agent) for agent in agents]
        votes = await asyncio.gather(*tasks)
        return [v for v in votes if v is not None]
    
    def _print_results(self, votes: List[AgentVote], consensus: dict, elapsed: float):
        """Print beautiful results table."""
        table = Table(
            title="🏦 AGENT VOTE SUMMARY",
            show_header=True,
            header_style="bold magenta"
        )
        table.add_column("Agent", style="cyan", width=35)
        table.add_column("Type", style="dim", width=18)
        table.add_column("Direction", justify="center", width=8)
        table.add_column("Conviction", justify="right", width=10)
        table.add_column("Primary Driver", width=30)
        
        for vote in sorted(votes, key=lambda v: v.conviction, reverse=True)[:15]:
            direction_style = {
                "LONG": "bold green",
                "SHORT": "bold red",
                "NEUTRAL": "yellow",
                "NO_TRADE": "dim"
            }.get(vote.direction, "white")
            
            table.add_row(
                vote.agent_name[:34],
                vote.agent_type[:17],
                f"[{direction_style}]{vote.direction}[/{direction_style}]",
                f"{vote.conviction:.2f}",
                vote.primary_driver[:29]
            )
        
        console.print(table)
        
        # Consensus box
        signal = consensus.get("final_signal", "NO_TRADE")
        signal_color = "green" if signal == "LONG" else "red" if signal == "SHORT" else "yellow"
        
        console.print(f"\n{'='*60}")
        console.print(f"  [bold]CONSENSUS SIGNAL: [{signal_color}]{signal}[/{signal_color}][/bold]")
        console.print(f"  Long %: {consensus['long_pct']:.1%}  |  "
                     f"Short %: {consensus['short_pct']:.1%}  |  "
                     f"Neutral %: {consensus['neutral_pct']:.1%}")
        console.print(f"  Weighted Conviction: {consensus['weighted_conviction']:.3f}")
        console.print(f"  Threshold Met: {'✅ YES' if consensus['threshold_met'] else '❌ NO'}")
        console.print(f"  Quality Score: {consensus['quality_score']:.2f}/1.0")
        console.print(f"  Run Time: {elapsed:.1f}s | "
                     f"Agents Completed: {len(votes)}")
        console.print(f"{'='*60}\n")