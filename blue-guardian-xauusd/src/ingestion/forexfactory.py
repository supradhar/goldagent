# Placeholder for ForexFactory ingestion logic
# src/ingestion/forexfactory.py
"""
ForexFactory High-Impact News Scraper
Pulls 'Red Folder' events (highest impact) for USD and gold-relevant currencies.
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import aiohttp
from bs4 import BeautifulSoup
import feedparser
from loguru import logger
from pydantic import BaseModel


class EconomicEvent(BaseModel):
    event_id: str
    datetime_utc: str
    currency: str
    impact: str          # "High" | "Medium" | "Low"
    event_name: str
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    surprise_direction: Optional[str] = None  # "beat" | "miss" | "inline"
    surprise_magnitude: Optional[float] = None
    gold_relevance_score: float = 0.0
    notes: str = ""


# Events that most directly move gold
GOLD_RELEVANT_EVENTS = {
    "Non-Farm Payrolls": 0.95,
    "CPI": 0.95,
    "Core CPI": 0.90,
    "Federal Funds Rate": 1.0,
    "FOMC Statement": 1.0,
    "FOMC Meeting Minutes": 0.85,
    "Fed Chair Press Conference": 0.90,
    "PCE Price Index": 0.85,
    "Core PCE Price Index": 0.85,
    "GDP": 0.75,
    "PPI": 0.75,
    "Retail Sales": 0.70,
    "ISM Manufacturing PMI": 0.65,
    "ISM Services PMI": 0.65,
    "Initial Jobless Claims": 0.60,
    "ADP Non-Farm Employment Change": 0.65,
    "Treasury Yields": 0.80,
    "DXY": 0.85,
    "Unemployment Rate": 0.80,
    "Average Hourly Earnings": 0.85,
    "Fed Speak": 0.75,
    "Geopolitical Risk": 0.85,
}


class ForexFactoryScraper:
    """
    Scrapes ForexFactory for upcoming high-impact USD events.
    Uses their calendar API endpoint + RSS feed as fallback.
    """
    
    BASE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    BACKUP_URL = "https://www.forexfactory.com/calendar.php"
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; BlueGuardianBot/1.0)",
            "Accept": "application/json"
        }
    
    async def fetch_week_events(self) -> List[EconomicEvent]:
        """Fetch all events for the current week."""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(self.BASE_URL, timeout=10) as resp:
                    data = await resp.json(content_type=None)
                    return self._parse_ff_json(data)
            except Exception as e:
                logger.warning(f"FF JSON failed: {e}, trying backup")
                return await self._scrape_html(session)
    
    def _parse_ff_json(self, data: List[Dict]) -> List[EconomicEvent]:
        """Parse ForexFactory JSON format."""
        events = []
        for item in data:
            if item.get("impact") not in ("High",):  # Red folder only
                continue
            if item.get("currency") not in ("USD", "XAU"):
                continue
            
            event_name = item.get("title", "")
            relevance = self._compute_gold_relevance(event_name, item.get("currency"))
            
            # Parse surprise
            actual = item.get("actual", "")
            forecast = item.get("forecast", "")
            surprise_dir, surprise_mag = self._compute_surprise(
                actual, forecast, event_name
            )
            
            events.append(EconomicEvent(
                event_id=f"ff_{item.get('id', '')}",
                datetime_utc=item.get("date", ""),
                currency=item.get("currency", ""),
                impact="High",
                event_name=event_name,
                forecast=forecast,
                previous=item.get("previous", ""),
                actual=actual,
                surprise_direction=surprise_dir,
                surprise_magnitude=surprise_mag,
                gold_relevance_score=relevance,
                notes=item.get("detail", "")
            ))
        
        logger.info(f"Fetched {len(events)} high-impact events")
        return events
    
    def _compute_gold_relevance(self, event_name: str, currency: str) -> float:
        """Score how relevant an event is to gold price movement."""
        for keyword, score in GOLD_RELEVANT_EVENTS.items():
            if keyword.lower() in event_name.lower():
                return score
        # USD events always have some relevance (inverse DXY/gold relationship)
        if currency == "USD":
            return 0.50
        return 0.30
    
    def _compute_surprise(
        self, actual: str, forecast: str, event_name: str
    ) -> tuple:
        """Compute surprise direction and magnitude."""
        try:
            act_val = float(actual.replace("%", "").replace("K", "").replace("M", ""))
            fore_val = float(forecast.replace("%", "").replace("K", "").replace("M", ""))
            diff = act_val - fore_val
            magnitude = abs(diff / fore_val) if fore_val != 0 else 0
            
            direction = "inline"
            if magnitude > 0.01:
                direction = "beat" if diff > 0 else "miss"
            
            return direction, round(magnitude, 4)
        except (ValueError, ZeroDivisionError):
            return None, None
    
    async def _scrape_html(self, session) -> List[EconomicEvent]:
        """Fallback: scrape HTML directly."""
        logger.info("Using HTML scrape fallback")
        events = []
        try:
            async with session.get(
                "https://www.forexfactory.com/calendar",
                timeout=15
            ) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                # Parse calendar table — simplified
                rows = soup.find_all('tr', class_='calendar_row')
                for row in rows:
                    impact = row.find('td', class_='impact')
                    if not impact or 'icon--ff-impact-red' not in str(impact):
                        continue
                    # Extract fields...
                    # (full implementation would parse each cell)
        except Exception as e:
            logger.error(f"HTML scrape failed: {e}")
        return events


async def get_todays_red_folder_events() -> List[EconomicEvent]:
    """Main entry point: get today's high-impact events."""
    scraper = ForexFactoryScraper()
    all_events = await scraper.fetch_week_events()
    
    today = datetime.utcnow().date()
    todays = [
        e for e in all_events 
        if e.datetime_utc and today.isoformat() in e.datetime_utc
    ]
    
    logger.info(f"Today's red-folder events: {len(todays)}")
    for e in todays:
        logger.info(f"  {e.datetime_utc} | {e.event_name} | relevance={e.gold_relevance_score}")
    
    return todays