# Placeholder for ingestion pipeline logic
# src/ingestion/pipeline.py
"""
Daily data pipeline orchestrator.
Runs all ingestion tasks and populates the knowledge graph.
"""
import asyncio
from datetime import datetime
from loguru import logger
from .forexfactory import ForexFactoryScraper, get_todays_red_folder_events
from .fed_speeches import FedSpeechScraper
from .market_data import MarketDataFetcher
from ..knowledge_graph.graph_builder import XAUUSDGraphBuilder
import os


class DailyDataPipeline:
    """
    Orchestrates all data ingestion for the morning simulation.
    Should be run at ~5:00 AM PST (30 minutes before simulation).
    """
    
    def __init__(self):
        self.ff_scraper = ForexFactoryScraper()
        self.fed_scraper = FedSpeechScraper()
        self.market_fetcher = MarketDataFetcher()
        self.graph = XAUUSDGraphBuilder(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USER"),
            password=os.getenv("NEO4J_PASSWORD")
        )
    
    async def run_full_pipeline(self) -> dict:
        """
        Full morning pipeline. Returns summary of ingested data.
        Expected runtime: 2-4 minutes.
        """
        start = datetime.now()
        logger.info("=== STARTING DAILY DATA PIPELINE ===")
        results = {}
        
        # 1. Market snapshot (fastest — always run first)
        logger.info("Step 1/4: Fetching market snapshot...")
        snapshot = await self.market_fetcher.get_full_snapshot()
        results["market_snapshot"] = snapshot
        logger.info(f"  XAUUSD: ${snapshot.xauusd_price:.2f} | "
                    f"DXY: {snapshot.dxy_price:.2f} | "
                    f"10Y Yield: {snapshot.us_10y_yield:.2f}%")
        
        # 2. ForexFactory red-folder events
        logger.info("Step 2/4: Fetching ForexFactory events...")
        ff_events = await get_todays_red_folder_events()
        n_events = self.graph.ingest_economic_events(ff_events)
        snapshot.high_impact_events_today = n_events
        results["ff_events"] = ff_events
        logger.info(f"  Ingested {n_events} high-impact events")
        
        # 3. Fed speeches (last 7 days)
        logger.info("Step 3/4: Fetching Fed speeches...")
        fed_docs = await self.fed_scraper.fetch_recent_speeches(days_back=7)
        for doc in fed_docs:
            self.graph.ingest_fed_document(doc)
        results["fed_docs"] = fed_docs
        logger.info(f"  Ingested {len(fed_docs)} Fed documents")
        
        # 4. Generate knowledge context for agents
        logger.info("Step 4/4: Building knowledge context...")
        kg_context = self.graph.query_relevant_context(snapshot)
        results["kg_context"] = kg_context
        
        elapsed = (datetime.now() - start).total_seconds()
        logger.info(f"=== PIPELINE COMPLETE in {elapsed:.1f}s ===")
        
        # Save pipeline output for simulation
        results["pipeline_timestamp"] = datetime.now().isoformat()
        return results