# src/agents/memory_agent.py
"""
Extension: Agents with persistent memory across trading sessions.
Uses Zep for long-term memory storage and retrieval.
"""
import os
from zep_python import ZepClient, Memory, Message
from loguru import logger


class MemoryEnabledAgent:
    """
    Agent extension that maintains episodic memory across sessions.
    Each agent remembers past predictions and outcomes.
    """
    
    def __init__(self, agent_config: dict):
        super().__init__(agent_config)
        self.zep = ZepClient(
            api_key=os.getenv("ZEP_API_KEY"),
            base_url=os.getenv("ZEP_BASE_URL", "http://localhost:8000")
        )
        self.session_id = f"agent_{agent_config['agent_id']}"
    
    async def store_prediction_memory(self, vote, actual_outcome: dict):
        """
        Store agent's prediction and the actual market outcome.
        Called after trade resolution.
        """
        was_correct = (
            (vote.direction == "LONG" and actual_outcome.get("move_pct", 0) > 0.3) or
            (vote.direction == "SHORT" and actual_outcome.get("move_pct", 0) < -0.3)
        )
        
        memory_text = (
            f"On {actual_outcome['date']}, I predicted {vote.direction} with "
            f"conviction {vote.conviction:.2f}. Reasoning: {vote.entry_rationale[:200]}. "
            f"Actual move: {actual_outcome.get('move_pct', 0):+.2f}%. "
            f"Was I correct? {'YES' if was_correct else 'NO'}. "
            f"Key insight: {actual_outcome.get('post_hoc_analysis', 'N/A')}"
        )
        
        await self.zep.memory.aadd_memory(
            session_id=self.session_id,
            memory=Memory(messages=[
                Message(role="assistant", content=memory_text)
            ])
        )
        logger.debug(f"Agent {self.name} memory stored: {'✓' if was_correct else '✗'}")
    
    async def recall_relevant_memories(self, market_context: str) -> str:
        """
        Search agent's memory for relevant past experiences.
        Returns top 3 most relevant memories as context.
        """
        try:
            results = await self.zep.memory.asearch_memory(
                session_id=self.session_id,
                query=market_context,
                limit=3
            )
            
            if not results or not results.results:
                return ""
            
            memory_context = "\nMY RELEVANT PAST EXPERIENCES:\n"
            for r in results.results:
                memory_context += f"• {r.message.content[:200]}\n"
            
            return memory_context
        except Exception as e:
            logger.debug(f"Memory recall failed for {self.name}: {e}")
            return ""