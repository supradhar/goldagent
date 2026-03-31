# Placeholder for consensus logic
# src/simulation/consensus.py
"""
Aggregates agent votes into a single tradeable signal.
Applies conviction weighting, type weighting, and quality filters.
"""
from typing import List, Dict
import numpy as np
from loguru import logger
from ..agents.base_agent import AgentVote


# How much weight to give each agent type in final consensus
AGENT_TYPE_WEIGHTS = {
    "macro_hedge_fund":       2.5,   # Highest weight — sophisticated, macro view
    "cta_trend_follower":     2.0,   # Systematic, reliable for momentum
    "central_bank_buyer":     2.0,   # Structural, long-horizon signal
    "physical_dealer":        1.8,   # Real supply/demand signal
    "market_maker_hft":       1.5,   # Flow signal, leading indicator
    "family_office_geopolitical": 1.5,
    "technical_momentum":     1.5,   # Reliable technical signal
    "sovereign_wealth_fund":  2.0,
    "quant_fund":             1.8,
    "retail_emotional":       0.3,   # Contrarian weight (fade retail)
    "options_market_maker":   1.5,
    "default":                1.0,
}

# Types where we apply CONTRARIAN logic (their LONG = our SHORT consideration)
CONTRARIAN_TYPES = {"retail_emotional", "newsletter_follower"}


class ConsensusEngine:
    """
    Multi-method consensus aggregation:
    1. Simple vote count (directional percentage)
    2. Conviction-weighted vote
    3. Type-weighted vote
    4. Combined quality score
    """
    
    def __init__(self):
        self.threshold = 0.80  # 80% agreement required
        self.min_conviction = 0.60  # Minimum weighted conviction for signal
        self.min_participating_agents = 10  # Need at least 10 agents
    
    def compute_consensus(
        self,
        votes: List[AgentVote],
        market_snapshot
    ) -> Dict:
        """Full consensus computation. Returns complete signal report."""
        
        # Filter out NO_TRADE and failed votes
        active_votes = [v for v in votes if v.direction not in ("NO_TRADE",)]
        tradeable_votes = [v for v in active_votes if v.would_trade_today]
        
        if len(tradeable_votes) < self.min_participating_agents:
            return self._no_signal_response(
                votes, f"Insufficient active agents ({len(tradeable_votes)})"
            )
        
        # Count directions
        long_votes = [v for v in tradeable_votes if v.direction == "LONG"]
        short_votes = [v for v in tradeable_votes if v.direction == "SHORT"]
        neutral_votes = [v for v in active_votes if v.direction == "NEUTRAL"]
        
        n = len(tradeable_votes)
        long_pct = len(long_votes) / n
        short_pct = len(short_votes) / n
        neutral_pct = len(neutral_votes) / len(active_votes) if active_votes else 0
        
        # Conviction-weighted vote
        long_conviction = self._weighted_conviction(long_votes, "LONG")
        short_conviction = self._weighted_conviction(short_votes, "SHORT")
        
        # Type-weighted aggregation
        type_weighted_long = self._type_weighted_score(tradeable_votes, "LONG")
        type_weighted_short = self._type_weighted_score(tradeable_votes, "SHORT")
        
        # Contrarian adjustment (retail herding in one direction = fade signal strengthens)
        contrarian_boost = self._compute_contrarian_boost(votes)
        
        # Final direction determination
        raw_long_score = (long_pct * 0.35 + long_conviction * 0.35 + type_weighted_long * 0.30)
        raw_short_score = (short_pct * 0.35 + short_conviction * 0.35 + type_weighted_short * 0.30)
        
        # Apply contrarian boost
        if contrarian_boost["fade_direction"] == "LONG":
            raw_long_score += contrarian_boost["magnitude"] * 0.1
        elif contrarian_boost["fade_direction"] == "SHORT":
            raw_short_score += contrarian_boost["magnitude"] * 0.1
        
        # Determine final signal
        dominant_score = max(raw_long_score, raw_short_score)
        dominant_direction = "LONG" if raw_long_score > raw_short_score else "SHORT"
        dominant_pct = long_pct if dominant_direction == "LONG" else short_pct
        
        # Apply threshold
        threshold_met = dominant_pct >= self.threshold
        conviction_met = dominant_score >= self.min_conviction
        
        final_signal = dominant_direction if (threshold_met and conviction_met) else "NO_TRADE"
        
        # Quality score (0-1)
        quality_score = self._compute_quality_score(
            votes, dominant_pct, dominant_score, market_snapshot
        )
        
        # Risk-adjusted conviction for position sizing
        risk_adjusted_conviction = dominant_score * quality_score
        
        # Compile blocking factors from NO_TRADE agents
        blocking_reasons = self._compile_blocking_reasons(votes)
        
        # Top long / short arguments
        top_long_rationale = self._top_rationales(long_votes, top_k=3)
        top_short_rationale = self._top_rationales(short_votes, top_k=3)
        
        return {
            "final_signal": final_signal,
            "dominant_direction": dominant_direction,
            "long_pct": long_pct,
            "short_pct": short_pct,
            "neutral_pct": neutral_pct,
            "long_votes": len(long_votes),
            "short_votes": len(short_votes),
            "neutral_votes": len(neutral_votes),
            "total_active": n,
            "weighted_conviction": round(dominant_score, 4),
            "risk_adjusted_conviction": round(risk_adjusted_conviction, 4),
            "quality_score": round(quality_score, 4),
            "threshold_met": threshold_met,
            "conviction_met": conviction_met,
            "contrarian_signal": contrarian_boost,
            "top_long_rationale": top_long_rationale,
            "top_short_rationale": top_short_rationale,
            "blocking_reasons": blocking_reasons,
            "suggested_entry_zone": self._consensus_entry_zone(
                long_votes if dominant_direction == "LONG" else short_votes
            ),
            "consensus_stop": self._consensus_stop(
                long_votes if dominant_direction == "LONG" else short_votes,
                dominant_direction
            ),
            "consensus_target": self._consensus_target(
                long_votes if dominant_direction == "LONG" else short_votes
            ),
        }
    
    def _weighted_conviction(self, votes: List[AgentVote], direction: str) -> float:
        """Average conviction among votes in this direction."""
        if not votes:
            return 0.0
        return float(np.mean([v.conviction for v in votes]))
    
    def _type_weighted_score(self, votes: List[AgentVote], direction: str) -> float:
        """Weight votes by agent type importance."""
        direction_votes = [v for v in votes if v.direction == direction]
        if not votes or not direction_votes:
            return 0.0
        
        total_weight = sum(
            AGENT_TYPE_WEIGHTS.get(v.agent_type, 1.0) for v in votes
        )
        direction_weight = sum(
            AGENT_TYPE_WEIGHTS.get(v.agent_type, 1.0) * v.conviction
            for v in direction_votes
        )
        
        return direction_weight / total_weight if total_weight > 0 else 0.0
    
    def _compute_contrarian_boost(self, votes: List[AgentVote]) -> dict:
        """
        If retail/emotional agents strongly favor one side,
        add a small contrarian boost to the OTHER side.
        (Retail is often on the wrong side of major moves.)
        """
        contrarian_votes = [
            v for v in votes 
            if v.agent_type in CONTRARIAN_TYPES and v.would_trade_today
        ]
        if len(contrarian_votes) < 2:
            return {"fade_direction": None, "magnitude": 0.0}
        
        retail_long = sum(1 for v in contrarian_votes if v.direction == "LONG")
        retail_short = sum(1 for v in contrarian_votes if v.direction == "SHORT")
        
        if retail_long / len(contrarian_votes) > 0.75:
            return {"fade_direction": "SHORT", "magnitude": 0.5}  # Fade retail long
        elif retail_short / len(contrarian_votes) > 0.75:
            return {"fade_direction": "LONG", "magnitude": 0.5}   # Fade retail short
        
        return {"fade_direction": None, "magnitude": 0.0}
    
    def _compute_quality_score(
        self, votes: List[AgentVote], pct: float, conviction: float, snapshot
    ) -> float:
        """
        Quality score considers:
        - Consensus strength (how decisive is the vote)
        - Agent diversity (are multiple types agreeing)
        - Market conditions (avoid trading into major news)
        - Current market session (NY overlap = highest quality)
        """
        scores = []
        
        # Vote decisiveness
        scores.append(min(1.0, (pct - 0.5) * 3))  # 0.5 → 0.0, 0.83 → 1.0
        
        # Agent diversity (count distinct types voting in dominant direction)
        dominant_dir = "LONG" if conviction > 0.5 else "SHORT"
        active = [v for v in votes if v.direction == dominant_dir and v.would_trade_today]
        type_diversity = len(set(v.agent_type for v in active)) / 8  # normalize to 8 types
        scores.append(min(1.0, type_diversity))
        
        # Session quality
        session_weights = {
            "New_York": 1.0, "Overlap": 0.9,
            "London": 0.75, "Asian": 0.5, "Off_Hours": 0.2
        }
        scores.append(session_weights.get(snapshot.xauusd_session, 0.5))
        
        # News risk penalty
        news_penalty = 1.0
        if snapshot.high_impact_events_today > 0 and \
                snapshot.next_event_in_minutes and \
                snapshot.next_event_in_minutes < 60:
            news_penalty = 0.4  # Heavy penalty if major news < 60min away
        scores.append(news_penalty)
        
        # Volatility appropriateness (avoid when VIX is extreme)
        if snapshot.vix > 30:
            scores.append(0.5)  # Penalty in extreme vol
        else:
            scores.append(1.0)
        
        return round(float(np.mean(scores)), 4)
    
    def _compile_blocking_reasons(self, votes: List[AgentVote]) -> List[str]:
        """Collect unique blocking factors from agents choosing not to trade."""
        reasons = []
        for vote in votes:
            if not vote.would_trade_today:
                reasons.extend(vote.blocking_factors)
        # Deduplicate and return top 5
        unique = list(dict.fromkeys(reasons))
        return unique[:5]
    
    def _top_rationales(self, votes: List[AgentVote], top_k: int = 3) -> List[str]:
        """Get top rationales by conviction."""
        sorted_votes = sorted(votes, key=lambda v: v.conviction, reverse=True)
        return [f"{v.agent_name}: {v.entry_rationale}" for v in sorted_votes[:top_k]]
    
    def _consensus_entry_zone(self, votes: List[AgentVote]) -> str:
        """Aggregate entry zones from top conviction votes."""
        if not votes:
            return "N/A"
        top = sorted(votes, key=lambda v: v.conviction, reverse=True)[:5]
        zones = [v.suggested_entry_zone for v in top if v.suggested_entry_zone != "N/A"]
        return zones[0] if zones else "N/A"
    
    def _consensus_stop(self, votes: List[AgentVote], direction: str) -> str:
        if not votes:
            return "N/A"
        top = sorted(votes, key=lambda v: v.conviction, reverse=True)[:3]
        stops = [v.suggested_stop_loss for v in top if v.suggested_stop_loss != "N/A"]
        return stops[0] if stops else "N/A"
    
    def _consensus_target(self, votes: List[AgentVote]) -> str:
        if not votes:
            return "N/A"
        top = sorted(votes, key=lambda v: v.conviction, reverse=True)[:3]
        targets = [v.suggested_target for v in top if v.suggested_target != "N/A"]
        return targets[0] if targets else "N/A"
    
    def _no_signal_response(self, votes: List[AgentVote], reason: str) -> dict:
        return {
            "final_signal": "NO_TRADE",
            "dominant_direction": "NEUTRAL",
            "long_pct": 0.0, "short_pct": 0.0, "neutral_pct": 1.0,
            "long_votes": 0, "short_votes": 0, "neutral_votes": len(votes),
            "total_active": len(votes),
            "weighted_conviction": 0.0,
            "risk_adjusted_conviction": 0.0,
            "quality_score": 0.0,
            "threshold_met": False, "conviction_met": False,
            "reason": reason,
            "contrarian_signal": {"fade_direction": None, "magnitude": 0.0},
            "top_long_rationale": [], "top_short_rationale": [],
            "blocking_reasons": [reason],
            "suggested_entry_zone": "N/A",
            "consensus_stop": "N/A",
            "consensus_target": "N/A",
        }