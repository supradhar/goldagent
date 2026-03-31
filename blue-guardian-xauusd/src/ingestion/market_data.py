# Placeholder for Market Data ingestion logic
# src/ingestion/market_data.py
"""
Real-time and historical market data for the simulation.
"""
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
import aiohttp
import pandas as pd
import numpy as np
from loguru import logger
from pydantic import BaseModel
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
from fredapi import Fred


class MarketSnapshot(BaseModel):
    """Complete market state injected into each simulation run."""
    timestamp: str
    
    # Gold
    xauusd_price: float
    xauusd_change_1h: float
    xauusd_change_24h: float
    xauusd_atr_14: float          # 14-period ATR on H1
    xauusd_volume_relative: float # vs 20-day average
    xauusd_above_200ma: bool
    xauusd_above_50ma: bool
    xauusd_rsi_14: float
    xauusd_session: str           # Asian | London | New_York | Overlap
    
    # DXY / Dollar
    dxy_price: float
    dxy_change_1d: float
    dxy_trend: str                # "uptrend" | "downtrend" | "ranging"
    
    # Yields (most impactful on gold)
    us_10y_yield: float
    us_2y_yield: float
    yield_curve_spread: float     # 10y - 2y
    real_yield_10y: float        # 10y nominal - breakeven inflation
    
    # Risk environment
    vix: float
    vix_trend: str                # rising | falling | stable
    spx_change_1d: float
    
    # Macro context
    fed_funds_rate: float
    breakeven_inflation_10y: float
    
    # Today's events
    high_impact_events_today: int
    next_event_in_minutes: Optional[int] = None
    last_cpi_surprise: Optional[float] = None
    last_nfp_surprise: Optional[float] = None
    
    # Derived signals
    risk_environment: str         # "risk_on" | "risk_off" | "mixed"
    dollar_gold_divergence: bool  # DXY and gold moving same direction (unusual)
    real_yield_direction: str     # "rising" (bearish gold) | "falling" (bullish gold)


class MarketDataFetcher:
    """
    Fetches all required market data for the simulation.
    Uses OANDA + FRED + FMP with fallbacks.
    """
    
    def __init__(self):
        self.oanda_api = oandapyV20.API(
            access_token=os.getenv("OANDA_API_KEY"),
            environment=os.getenv("OANDA_ENVIRONMENT", "practice")
        )
        self.fred = Fred(api_key=os.getenv("FRED_API_KEY"))
        self.fmp_key = os.getenv("FMP_API_KEY")
        self.polygon_key = os.getenv("POLYGON_API_KEY")
    
    async def get_full_snapshot(self) -> MarketSnapshot:
        """Fetch all data and build complete market snapshot."""
        logger.info("Fetching market snapshot...")
        
        async with aiohttp.ClientSession() as session:
            # Fetch all data concurrently
            xau_data, dxy_data, yields_data, risk_data = await asyncio.gather(
                self._fetch_xauusd(session),
                self._fetch_dxy(session),
                self._fetch_yields(),
                self._fetch_risk_metrics(session),
            )
        
        # Compute derived signals
        real_yield = yields_data["us_10y"] - yields_data.get("breakeven_10y", 2.0)
        yield_curve = yields_data["us_10y"] - yields_data["us_2y"]
        
        # Risk environment classification
        risk_env = self._classify_risk_environment(
            dxy_data["change_1d"],
            risk_data["vix"],
            risk_data["spx_change_1d"]
        )
        
        # Real yield direction (key driver)
        real_yield_dir = "rising" if real_yield > yields_data.get("prev_real_yield", real_yield) else "falling"
        
        return MarketSnapshot(
            timestamp=datetime.utcnow().isoformat(),
            xauusd_price=xau_data["price"],
            xauusd_change_1h=xau_data["change_1h"],
            xauusd_change_24h=xau_data["change_24h"],
            xauusd_atr_14=xau_data["atr_14"],
            xauusd_volume_relative=xau_data.get("vol_relative", 1.0),
            xauusd_above_200ma=xau_data["above_200ma"],
            xauusd_above_50ma=xau_data["above_50ma"],
            xauusd_rsi_14=xau_data["rsi"],
            xauusd_session=self._get_current_session(),
            dxy_price=dxy_data["price"],
            dxy_change_1d=dxy_data["change_1d"],
            dxy_trend=dxy_data["trend"],
            us_10y_yield=yields_data["us_10y"],
            us_2y_yield=yields_data["us_2y"],
            yield_curve_spread=yield_curve,
            real_yield_10y=real_yield,
            vix=risk_data["vix"],
            vix_trend=risk_data["vix_trend"],
            spx_change_1d=risk_data["spx_change_1d"],
            fed_funds_rate=yields_data.get("fed_funds", 5.25),
            breakeven_inflation_10y=yields_data.get("breakeven_10y", 2.0),
            high_impact_events_today=0,  # filled by pipeline
            risk_environment=risk_env,
            dollar_gold_divergence=self._check_divergence(
                dxy_data["change_1d"], xau_data["change_24h"]
            ),
            real_yield_direction=real_yield_dir
        )
    
    async def _fetch_xauusd(self, session) -> Dict:
        """Fetch XAUUSD OHLCV + indicators via OANDA."""
        try:
            # Get H1 candles (last 200 for MAs + ATR)
            r = instruments.InstrumentsCandles(
                instrument="XAU_USD",
                params={"granularity": "H1", "count": 200, "price": "MBA"}
            )
            self.oanda_api.request(r)
            candles = r.response["candles"]
            
            closes = np.array([float(c["mid"]["c"]) for c in candles if c["complete"]])
            highs = np.array([float(c["mid"]["h"]) for c in candles if c["complete"]])
            lows = np.array([float(c["mid"]["l"]) for c in candles if c["complete"]])
            
            current_price = float(candles[-1]["mid"]["c"])
            
            return {
                "price": current_price,
                "change_1h": (current_price - closes[-2]) / closes[-2] * 100,
                "change_24h": (current_price - closes[-25]) / closes[-25] * 100,
                "atr_14": self._compute_atr(highs, lows, closes, period=14),
                "above_200ma": current_price > closes[-200:].mean(),
                "above_50ma": current_price > closes[-50:].mean(),
                "rsi": self._compute_rsi(closes, period=14),
            }
        except Exception as e:
            logger.error(f"OANDA fetch failed: {e}")
            return await self._fetch_xauusd_fallback(session)
    
    async def _fetch_xauusd_fallback(self, session) -> Dict:
        """Fallback: use FMP for gold data."""
        url = f"https://financialmodelingprep.com/api/v3/quote/XAUUSD?apikey={self.fmp_key}"
        async with session.get(url) as resp:
            data = await resp.json()
            if data:
                q = data[0]
                return {
                    "price": q.get("price", 2000.0),
                    "change_1h": 0.0,
                    "change_24h": q.get("changesPercentage", 0.0),
                    "atr_14": q.get("price", 2000.0) * 0.008,  # ~0.8% estimate
                    "above_200ma": q.get("priceAvg200", 0) < q.get("price", 0),
                    "above_50ma": q.get("priceAvg50", 0) < q.get("price", 0),
                    "rsi": 50.0,  # neutral fallback
                }
        return {"price": 2000.0, "change_1h": 0.0, "change_24h": 0.0,
                "atr_14": 16.0, "above_200ma": True, "above_50ma": True, "rsi": 50.0}
    
    async def _fetch_yields(self) -> Dict:
        """Fetch Treasury yields via FRED."""
        try:
            loop = asyncio.get_event_loop()
            # FRED series
            data_10y = await loop.run_in_executor(
                None, lambda: self.fred.get_series_latest_release("GS10")
            )
            data_2y = await loop.run_in_executor(
                None, lambda: self.fred.get_series_latest_release("GS2")
            )
            data_breakeven = await loop.run_in_executor(
                None, lambda: self.fred.get_series_latest_release("T10YIE")
            )
            data_ffr = await loop.run_in_executor(
                None, lambda: self.fred.get_series_latest_release("FEDFUNDS")
            )
            return {
                "us_10y": float(data_10y.iloc[-1]),
                "us_2y": float(data_2y.iloc[-1]),
                "breakeven_10y": float(data_breakeven.iloc[-1]),
                "fed_funds": float(data_ffr.iloc[-1]),
            }
        except Exception as e:
            logger.warning(f"FRED fetch failed: {e}, using defaults")
            return {"us_10y": 4.5, "us_2y": 4.8, "breakeven_10y": 2.3, "fed_funds": 5.25}
    
    async def _fetch_dxy(self, session) -> Dict:
        """Fetch DXY data."""
        url = f"https://financialmodelingprep.com/api/v3/quote/%5EDXY?apikey={self.fmp_key}"
        try:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                if data:
                    q = data[0]
                    price = q.get("price", 104.0)
                    change = q.get("changesPercentage", 0.0)
                    return {
                        "price": price,
                        "change_1d": change,
                        "trend": "uptrend" if change > 0.3 else "downtrend" if change < -0.3 else "ranging"
                    }
        except Exception as e:
            logger.warning(f"DXY fetch failed: {e}")
        return {"price": 104.0, "change_1d": 0.0, "trend": "ranging"}
    
    async def _fetch_risk_metrics(self, session) -> Dict:
        """Fetch VIX, SPX."""
        try:
            vix_url = f"https://financialmodelingprep.com/api/v3/quote/%5EVIX?apikey={self.fmp_key}"
            spx_url = f"https://financialmodelingprep.com/api/v3/quote/%5EGSPC?apikey={self.fmp_key}"
            
            async with session.get(vix_url, timeout=8) as r1, \
                       session.get(spx_url, timeout=8) as r2:
                vix_data = await r1.json()
                spx_data = await r2.json()
                
                vix = vix_data[0]["price"] if vix_data else 18.0
                vix_prev = vix_data[0].get("previousClose", vix) if vix_data else vix
                spx_chg = spx_data[0].get("changesPercentage", 0.0) if spx_data else 0.0
                
                return {
                    "vix": vix,
                    "vix_trend": "rising" if vix > vix_prev * 1.02 else "falling" if vix < vix_prev * 0.98 else "stable",
                    "spx_change_1d": spx_chg
                }
        except Exception as e:
            logger.warning(f"Risk metrics fetch failed: {e}")
        return {"vix": 18.0, "vix_trend": "stable", "spx_change_1d": 0.0}
    
    @staticmethod
    def _compute_atr(highs, lows, closes, period=14) -> float:
        """Standard ATR calculation."""
        true_ranges = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        if len(true_ranges) < period:
            return closes[-1] * 0.008
        return float(np.mean(true_ranges[-period:]))
    
    @staticmethod
    def _compute_rsi(closes, period=14) -> float:
        """Standard RSI calculation."""
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)
    
    @staticmethod
    def _get_current_session() -> str:
        """Determine current forex trading session (UTC)."""
        hour = datetime.utcnow().hour
        if 22 <= hour or hour < 7:
            return "Asian"
        elif 7 <= hour < 12:
            return "London"
        elif 12 <= hour < 17:
            return "New_York"
        elif 17 <= hour < 22:
            return "Overlap"
        return "Off_Hours"
    
    @staticmethod
    def _classify_risk_environment(dxy_change, vix, spx_change) -> str:
        """Classify risk-on / risk-off environment."""
        risk_off_signals = (vix > 20, dxy_change > 0.3, spx_change < -0.5)
        risk_on_signals = (vix < 16, dxy_change < -0.2, spx_change > 0.5)
        
        if sum(risk_off_signals) >= 2:
            return "risk_off"
        elif sum(risk_on_signals) >= 2:
            return "risk_on"
        return "mixed"
    
    @staticmethod
    def _check_divergence(dxy_change, xau_change) -> bool:
        """Check if DXY and gold are moving in the same direction (unusual)."""
        return (dxy_change > 0 and xau_change > 0) or (dxy_change < 0 and xau_change < 0)