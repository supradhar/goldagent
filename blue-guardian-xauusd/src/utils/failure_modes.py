# src/utils/failure_modes.py
"""
Common failure modes and their mitigations.
"""

FAILURE_MODES = {
    
    "API_RATE_LIMIT": {
        "symptom": "Anthropic API returns 429 errors, agents timeout",
        "probability": "Medium (if running many agents)",
        "impact": "Simulation incomplete, consensus unreliable",
        "mitigation": [
            "Use tenacity retry with exponential backoff (already in base_agent.py)",
            "Reduce SIMULATION_WORKERS to 4 (slower but reliable)",
            "Switch to Ollama for cost-free unlimited calls",
            "Pre-cache recent responses for similar market conditions"
        ]
    },
    
    "NEO4J_CONNECTION_LOST": {
        "symptom": "Knowledge graph queries fail, agents get empty context",
        "probability": "Low (local) / Medium (cloud)",
        "impact": "Agents deliberate without historical context (degraded quality)",
        "mitigation": [
            "Fallback: use last successful kg_context (cache in Redis)",
            "Neo4j has automatic reconnect built in",
            "Run health check in validate_system.py before simulation starts"
        ]
    },
    
    "OANDA_DATA_STALE": {
        "symptom": "Price feed shows data > 15 min old",
        "probability": "Low",
        "impact": "Agents deliberate on wrong price → invalid trade levels",
        "mitigation": [
            "Timestamp check: reject data > 5 min old",
            "Fallback to FMP API for price",
            "NEVER execute trade if price freshness cannot be confirmed"
        ]
    },
    
    "LLM_HALLUCINATION": {
        "symptom": "Agent returns malformed JSON, impossible price levels, nonsensical reasoning",
        "probability": "Medium (3-5% of agent calls)",
        "impact": "Individual agent vote corrupted",
        "mitigation": [
            "JSON schema validation on every vote (already in _parse_vote)",
            "Price sanity check: entry must be within 2% of current price",
            "Fallback to NO_TRADE for any agent that fails validation",
            "Log all malformed outputs for model improvement"
        ]
    },
    
    "CONSENSUS_INSTABILITY": {
        "symptom": "Consensus flips between LONG/SHORT on similar market states",
        "probability": "Medium (in ranging/mixed markets)",
        "impact": "False signals, overtrading",
        "mitigation": [
            "Require 80% threshold (already enforced)",
            "Add 'consensus streak' requirement: signal only valid if 3 consecutive morning sims agree",
            "Quality score below 0.65 → auto-skip regardless of direction",
            "Track consensus vs actual move: if accuracy < 55% in last 10 signals, pause system"
        ]
    },
    
    "BLUE_GUARDIAN_COMPLIANCE": {
        "symptom": "Risk manager flags potential violation",
        "probability": "Low (if rules followed)",
        "impact": "Challenge disqualification",
        "mitigation": [
            "guardian_compliance_check runs before EVERY signal",
            "Hard coded: TradersPost payload always has require_manual_confirmation=True",
            "Daily drawdown displayed prominently in terminal output",
            "Never run morning_run.py without reading risk state first"
        ]
    },
    
    "MARKET_REGIME_MISMATCH": {
        "symptom": "System built on macro assumptions, but market is in pure technical range",
        "probability": "Medium (30% of trading days)",
        "impact": "Lower signal quality, more false breakouts",
        "mitigation": [
            "ADX filter: if ADX < 20 on H4, quality_score is automatically penalized",
            "CTA trend system (AG002) will vote NO_TRADE in ranging market",
            "Trust quality_score: if < 0.60, skip the trade"
        ]
    }
}