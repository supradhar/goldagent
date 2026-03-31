# src/simulation/advanced_ensemble.py
"""
Advanced ensemble methods for more sophisticated consensus.
"""
import numpy as np
from typing import List
from ..agents.base_agent import AgentVote


class AdvancedConsensusEngine:
    """
    Extensions to the base consensus engine.
    """
    
    def superforecaster_aggregation(self, votes: List[AgentVote]) -> float:
        """
        Extremized aggregation (Satopää et al. 2014):
        Works better than simple averaging because individual agents 
        are under-confident. Extremize toward 0/1.
        """
        # Get probability of LONG for each agent
        probs = []
        for vote in votes:
            if vote.direction == "LONG":
                probs.append(0.5 + vote.conviction * 0.5)
            elif vote.direction == "SHORT":
                probs.append(0.5 - vote.conviction * 0.5)
            else:
                probs.append(0.5)
        
        if not probs:
            return 0.5
        
        # Extremize: LogOdds mean, then extremize parameter α=2.5
        alpha = 2.5
        log_odds = [np.log(p / (1 - p + 1e-10)) for p in probs]
        mean_log_odds = np.mean(log_odds)
        extremized_log_odds = mean_log_odds * alpha
        
        return 1 / (1 + np.exp(-extremized_log_odds))
    
    def diversity_bonus(self, votes: List[AgentVote]) -> float:
        """
        Hong-Page diversity theorem implementation:
        More accurate ensemble = diverse perspectives, not just smart forecasters.
        Bonus when disagreeing sophisticated agents still align on direction.
        """
        macro_agents = [v for v in votes if "macro" in v.agent_type and v.would_trade_today]
        quant_agents = [v for v in votes if "cta" in v.agent_type or "quant" in v.agent_type and v.would_trade_today]
        fundamental_agents = [v for v in votes if "physical" in v.agent_type or "central_bank" in v.agent_type]
        
        groups = [macro_agents, quant_agents, fundamental_agents]
        majority_directions = []
        
        for group in groups:
            if not group:
                continue
            long_count = sum(1 for v in group if v.direction == "LONG")
            majority = "LONG" if long_count > len(group) / 2 else "SHORT"
            majority_directions.append(majority)
        
        if not majority_directions:
            return 1.0
        
        # If all groups agree → high diversity bonus
        if len(set(majority_directions)) == 1:
            return 1.3  # 30% bonus to conviction
        elif len(set(majority_directions)) == 2:
            return 1.0  # No bonus
        else:
            return 0.85  # Penalty for complete disagreement