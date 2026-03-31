# src/simulation/market_state.py
from pydantic import BaseModel
from typing import Optional

class MarketSnapshot(BaseModel):
    """Complete market state injected into each simulation run."""
    timestamp: str
    
    # Gold
    xauusd_price: float
    xauusd_change_1h: float
    xauusd_change_24h: float
    xauusd_atr_14: float
    xauusd_volume_relative: float = 1.0
    xauusd_above_200ma: bool
    xauusd_above_50ma: bool
    xauusd_rsi_14: float
    xauusd_session: str
    
    # DXY / Dollar
    dxy_price: float
    dxy_change_1d: float
    dxy_trend: str
    
    # Yields
    us_10y_yield: float
    us_2y_yield: float
    yield_curve_spread: float
    real_yield_10y: float
    
    # Risk
    vix: float
    vix_trend: str
    spx_change_1d: float
    
    # Macro
    fed_funds_rate: float
    breakeven_inflation_10y: float
    high_impact_events_today: int
    next_event_in_minutes: Optional[int] = None
    last_cpi_surprise: Optional[float] = None
    last_nfp_surprise: Optional[float] = None
    
    # Derived
    risk_environment: str
    dollar_gold_divergence: bool
    real_yield_direction: str
    
    # Additional fields can be added here if necessary