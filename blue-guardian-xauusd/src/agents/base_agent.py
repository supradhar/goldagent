# Placeholder for base agent class
# src/agents/base_agent.py
"""
Abstract base class for all market participant agents.
"""
import os
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from pydantic import BaseModel
from anthropic import AsyncAnthropic
import aiohttp
from loguru import logger


class AgentVote(BaseModel):
    """The output of each agent's simulation deliberation."""
    agent_id: str
    agent_name: str
    agent_type: str
    
    # Core decision
    direction: str           # "LONG" | "SHORT" | "NEUTRAL" | "NO_TRADE"
    conviction: float        # 0.0 → 1.0
    
    # Entry/exit reasoning
    entry_rationale: str
    primary_driver: str      # Main reason for this trade direction
    
    # Risk parameters this agent would use
    suggested_entry_zone: str    # e.g., "$2,345–$2,350"
    suggested_stop_loss: str     # e.g., "below $2,330"
    suggested_target: str        # e.g., "$2,380"
    
    # Risk / behavioral flags
    would_trade_today: bool
    blocking_factors: List[str]  # Why they might NOT trade
    tail_risk_concern: str       # What could invalidate the thesis
    
    # Memory / experience reference
    similar_past_event: Optional[str] = None
    
    # Raw reasoning (for analysis)
    full_reasoning: str


class BaseAgent(ABC):
    """
    All 50-100 agents inherit from this.
    Key design: each agent has a fixed persona, memory, and decision framework.
    """
    
    def __init__(self, agent_config: dict):
        self.agent_id = agent_config["agent_id"]
        self.name = agent_config["name"]
        self.agent_type = agent_config["type"]
        self.persona_description = agent_config["persona"]
        self.trading_logic = agent_config["trading_logic"]
        self.risk_appetite = agent_config["risk_appetite"]  # "low"|"medium"|"high"
        self.memory_triggers = agent_config.get("memory_triggers", [])
        self.biases = agent_config.get("biases", [])
        self.time_horizon = agent_config.get("time_horizon", "intraday")
        
        # LLM client
        self._setup_llm()
    
    def _setup_llm(self):
        backend = os.getenv("LLM_BACKEND", "claude")
        if backend == "claude":
            self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            self.model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
            self.llm_type = "claude"
        else:
            self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            self.model = os.getenv("OLLAMA_MODEL", "llama3.1:70b")
            self.llm_type = "ollama"
    
    def build_system_prompt(self) -> str:
        """Build the agent's fixed persona prompt."""
        return f"""You are {self.name}, a specific type of gold market participant.

IDENTITY:
{self.persona_description}

YOUR TRADING LOGIC:
{self.trading_logic}

YOUR RISK APPETITE: {self.risk_appetite}
YOUR TIME HORIZON: {self.time_horizon}

YOUR KNOWN BIASES:
{chr(10).join(f'- {b}' for b in self.biases)}

YOUR MEMORY TRIGGERS (past events that strongly influence your decisions):
{chr(10).join(f'- {m}' for m in self.memory_triggers)}

TASK:
Given the current market state and knowledge context provided, you must decide:
1. Would you BUY (LONG), SELL (SHORT), or stay NEUTRAL/NO_TRADE on XAUUSD today?
2. What is your conviction level (0.0–1.0)?
3. What specific levels would you use (entry zone, stop, target)?
4. What would change your mind?

CRITICAL RULES:
- Stay in character at ALL times. Your decision must reflect YOUR type of participant.
- If the setup doesn't fit your mandate, say NO_TRADE — don't force it.
- Be specific about price levels (use the current price data given).
- Acknowledge uncertainty honestly.

OUTPUT FORMAT:
Respond with a JSON object ONLY. No other text.
{{
  "direction": "LONG|SHORT|NEUTRAL|NO_TRADE",
  "conviction": 0.0,
  "entry_rationale": "...",
  "primary_driver": "...",
  "suggested_entry_zone": "$X–$Y",
  "suggested_stop_loss": "below/above $Z",
  "suggested_target": "$W",
  "would_trade_today": true|false,
  "blocking_factors": ["..."],
  "tail_risk_concern": "...",
  "similar_past_event": "...",
  "full_reasoning": "..."
}}"""
    
    def build_user_prompt(self, market_snapshot, kg_context: str) -> str:
        """Build the market state prompt injected at runtime."""
        s = market_snapshot
        return f"""=== CURRENT MARKET STATE ===
Timestamp: {s.timestamp}

XAUUSD (Gold):
  Price: ${s.xauusd_price:,.2f}
  1H Change: {s.xauusd_change_1h:+.2f}%
  24H Change: {s.xauusd_change_24h:+.2f}%
  ATR(14) H1: ${s.xauusd_atr_14:.2f}
  RSI(14): {s.xauusd_rsi_14:.1f}
  Above 200MA: {'YES' if s.xauusd_above_200ma else 'NO'}
  Above 50MA: {'YES' if s.xauusd_above_50ma else 'NO'}
  Session: {s.xauusd_session}
  Volume vs Avg: {s.xauusd_volume_relative:.2f}x

US DOLLAR:
  DXY: {s.dxy_price:.2f} ({s.dxy_change_1d:+.2f}%)
  DXY Trend: {s.dxy_trend}
  DXY/Gold Divergence: {'YES (unusual!)' if s.dollar_gold_divergence else 'No'}

YIELDS & RATES:
  Fed Funds Rate: {s.fed_funds_rate:.2f}%
  US 10Y Yield: {s.us_10y_yield:.2f}%
  US 2Y Yield: {s.us_2y_yield:.2f}%
  Yield Curve (10-2): {s.yield_curve_spread:+.2f}%
  Real 10Y Yield: {s.real_yield_10y:.2f}%
  Real Yield Direction: {s.real_yield_direction}
  Breakeven Inflation: {s.breakeven_inflation_10y:.2f}%

RISK SENTIMENT:
  VIX: {s.vix:.2f} ({s.vix_trend})
  SPX 1D Change: {s.spx_change_1d:+.2f}%
  Environment: {s.risk_environment.upper()}

TODAY'S EVENTS:
  High-Impact Events: {s.high_impact_events_today}
  Next Event In: {f'{s.next_event_in_minutes}min' if s.next_event_in_minutes else 'None today'}
  Last CPI Surprise: {s.last_cpi_surprise or 'N/A'}
  Last NFP Surprise: {s.last_nfp_surprise or 'N/A'}

{kg_context}

=== YOUR DECISION ===
Based on ALL the above, what is YOUR trade decision as {self.name}?
Remember: stay strictly in character. Output ONLY valid JSON."""
    
    async def deliberate(self, market_snapshot, kg_context: str) -> AgentVote:
        """Main entry point: run agent deliberation."""
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(market_snapshot, kg_context)
        
        try:
            if self.llm_type == "claude":
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                raw_output = response.content[0].text
            else:
                raw_output = await self._ollama_complete(system_prompt, user_prompt)
            
            vote_data = self._parse_vote(raw_output)
            return AgentVote(
                agent_id=self.agent_id,
                agent_name=self.name,
                agent_type=self.agent_type,
                **vote_data
            )
        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            return self._fallback_vote()
    
    async def _ollama_complete(self, system_prompt: str, user_prompt: str) -> str:
        """Call local Ollama model."""
        import json as json_lib
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.3}
            }
            async with session.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=60
            ) as resp:
                data = await resp.json()
                return data["message"]["content"]
    
    def _parse_vote(self, raw_output: str) -> dict:
        """Parse LLM JSON output with fallback."""
        import json
        # Strip markdown fences if present
        raw = raw_output.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        data = json.loads(raw.strip())
        
        # Validate required fields
        assert data.get("direction") in ("LONG", "SHORT", "NEUTRAL", "NO_TRADE")
        assert 0.0 <= float(data.get("conviction", 0)) <= 1.0
        
        return data
    
    def _fallback_vote(self) -> AgentVote:
        """Safe fallback if LLM fails."""
        return AgentVote(
            agent_id=self.agent_id,
            agent_name=self.name,
            agent_type=self.agent_type,
            direction="NO_TRADE",
            conviction=0.0,
            entry_rationale="System error — agent unavailable",
            primary_driver="SYSTEM_ERROR",
            suggested_entry_zone="N/A",
            suggested_stop_loss="N/A",
            suggested_target="N/A",
            would_trade_today=False,
            blocking_factors=["Agent computation failed"],
            tail_risk_concern="Unknown",
            full_reasoning="Agent failed to deliberate"
        )