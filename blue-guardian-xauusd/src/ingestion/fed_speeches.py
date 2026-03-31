# Placeholder for Fed Speeches ingestion logic
# src/ingestion/fed_speeches.py
"""
Fed Speech & Communication Scraper
Sources: Fed.gov speeches, FOMC minutes, Beige Book
"""
import re
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
import aiohttp
from bs4 import BeautifulSoup
from loguru import logger
from pydantic import BaseModel


class FedDocument(BaseModel):
    doc_id: str
    doc_type: str      # speech | minutes | statement | beige_book | interview
    speaker: str
    title: str
    date: str
    url: str
    raw_text: str
    hawkish_dovish_signals: List[str] = []
    key_phrases: List[str] = []
    sentiment_score: float = 0.0   # -1 dovish → +1 hawkish
    gold_implication: str = ""     # bearish | bullish | neutral


# Key phrases that signal Fed stance toward gold
HAWKISH_PHRASES = [
    "sustained commitment to 2%", "further rate increases may be appropriate",
    "data dependent tightening", "not yet confident inflation returning",
    "higher for longer", "restrictive stance", "resilient labor market",
    "above-trend growth", "inflationary pressures remain",
]

DOVISH_PHRASES = [
    "rate cuts appropriate", "inflation making progress", "cooling labor market",
    "disinflation", "policy well positioned", "balance of risks",
    "slower pace of rate increases", "below target for some time",
    "financial conditions tightening substantially",
]


class FedSpeechScraper:
    """
    Scrapes Federal Reserve website for speeches and statements.
    """
    FED_SPEECHES_URL = "https://www.federalreserve.gov/newsevents/speech.htm"
    FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    
    def __init__(self):
        self.headers = {"User-Agent": "BlueGuardianResearch/1.0"}
    
    async def fetch_recent_speeches(self, days_back: int = 7) -> List[FedDocument]:
        """Fetch speeches from last N days."""
        docs = []
        async with aiohttp.ClientSession(headers=self.headers) as session:
            speech_links = await self._get_speech_links(session, days_back)
            tasks = [self._fetch_speech(session, url) for url in speech_links[:10]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            docs = [r for r in results if isinstance(r, FedDocument)]
        
        logger.info(f"Fetched {len(docs)} Fed speeches (last {days_back} days)")
        return docs
    
    async def _get_speech_links(
        self, session: aiohttp.ClientSession, days_back: int
    ) -> List[str]:
        """Parse speech index page for recent links."""
        try:
            async with session.get(self.FED_SPEECHES_URL, timeout=10) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                cutoff = datetime.now() - timedelta(days=days_back)
                links = []
                for row in soup.find_all('div', class_='col-xs-12'):
                    date_el = row.find('time')
                    link_el = row.find('a')
                    if date_el and link_el:
                        try:
                            doc_date = datetime.strptime(
                                date_el.get('datetime', ''), '%Y-%m-%d'
                            )
                            if doc_date >= cutoff:
                                href = link_el.get('href', '')
                                if href.startswith('/'):
                                    href = f"https://www.federalreserve.gov{href}"
                                links.append(href)
                        except ValueError:
                            pass
                return links
        except Exception as e:
            logger.error(f"Failed to fetch speech index: {e}")
            return []
    
    async def _fetch_speech(
        self, session: aiohttp.ClientSession, url: str
    ) -> FedDocument:
        """Fetch and parse a single speech."""
        async with session.get(url, timeout=15) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract metadata
            title = soup.find('h3', class_='title')
            title_text = title.get_text(strip=True) if title else "Unknown"
            
            speaker = soup.find('p', class_='speaker')
            speaker_text = speaker.get_text(strip=True) if speaker else "Federal Reserve"
            
            date_el = soup.find('p', class_='article__time')
            date_text = date_el.get_text(strip=True) if date_el else ""
            
            # Extract body text
            content = soup.find('div', id='content')
            raw_text = content.get_text(separator=' ', strip=True) if content else ""
            
            # Analyze sentiment
            hawkish_hits = [p for p in HAWKISH_PHRASES if p.lower() in raw_text.lower()]
            dovish_hits = [p for p in DOVISH_PHRASES if p.lower() in raw_text.lower()]
            
            # Sentiment score: +1 = very hawkish (bearish gold), -1 = very dovish (bullish gold)
            h_count = len(hawkish_hits)
            d_count = len(dovish_hits)
            total = h_count + d_count
            sentiment = (h_count - d_count) / total if total > 0 else 0.0
            
            # Gold implication
            if sentiment > 0.3:
                gold_implication = "bearish"  # hawkish = USD up = gold down
            elif sentiment < -0.3:
                gold_implication = "bullish"  # dovish = USD down = gold up
            else:
                gold_implication = "neutral"
            
            return FedDocument(
                doc_id=f"fed_{hash(url) % 99999}",
                doc_type="speech",
                speaker=speaker_text,
                title=title_text,
                date=date_text,
                url=url,
                raw_text=raw_text[:10000],  # cap at 10k chars
                hawkish_dovish_signals=hawkish_hits + dovish_hits,
                key_phrases=hawkish_hits + dovish_hits,
                sentiment_score=round(sentiment, 3),
                gold_implication=gold_implication
            )