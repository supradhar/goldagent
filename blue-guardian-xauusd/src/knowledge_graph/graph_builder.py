# Placeholder for knowledge graph builder logic
# src/knowledge_graph/graph_builder.py
"""
Builds and maintains the XAUUSD knowledge graph in Neo4j.
Nodes: Events, Entities, Concepts, Prices, Documents
Edges: CAUSES, CORRELATED_WITH, PRECEDES, IMPACTS, AUTHORED_BY
"""
from neo4j import GraphDatabase, Driver
from typing import List, Dict
from loguru import logger
from .embeddings import EmbeddingEngine


class XAUUSDGraphBuilder:
    """
    Core graph schema:
    
    (:EconomicEvent {name, date, surprise_pct, gold_move_after_1h})
    (:FedOfficial {name, role, current_stance})
    (:MarketRegime {name, description, start_date})
    (:Document {id, type, date, summary, embedding})
    (:PriceBar {timestamp, open, high, low, close, session})
    (:Concept {name, category}) -- e.g., "Real Yield Rising", "Safe Haven Demand"
    
    Relationships:
    (event)-[:CAUSED_MOVE {direction, magnitude_pct}]->(price_bar)
    (official)-[:AUTHORED]->(document)
    (document)-[:CONTAINS]->(concept)
    (concept)-[:CORRELATES_WITH {correlation, lookback_days}]->(price_bar)
    (event)-[:PRECEDES {hours}]->(event)
    """
    
    SCHEMA_QUERIES = [
        # Constraints
        "CREATE CONSTRAINT IF NOT EXISTS FOR (e:EconomicEvent) REQUIRE e.event_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:PriceBar) REQUIRE p.bar_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
        
        # Indexes for fast lookup
        "CREATE INDEX IF NOT EXISTS FOR (e:EconomicEvent) ON (e.date)",
        "CREATE INDEX IF NOT EXISTS FOR (p:PriceBar) ON (p.timestamp)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.doc_type)",
        
        # Full-text index for semantic search
        """CREATE FULLTEXT INDEX document_fulltext IF NOT EXISTS
           FOR (d:Document) ON EACH [d.raw_text, d.summary]""",
    ]
    
    def __init__(self, uri: str, user: str, password: str):
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        self.embedding_engine = EmbeddingEngine()
        logger.info("Neo4j connection established")
    
    def initialize_schema(self):
        """Create constraints and indexes."""
        with self.driver.session() as session:
            for query in self.SCHEMA_QUERIES:
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning(f"Schema init warning: {e}")
        
        # Seed core concepts
        self._seed_gold_concepts()
        logger.info("Schema initialized")
    
    def _seed_gold_concepts(self):
        """Pre-load known gold-relevant concepts."""
        concepts = [
            ("Real Yield Rising", "macro", "Increases opportunity cost of holding gold → bearish"),
            ("Real Yield Falling", "macro", "Decreases opportunity cost → bullish gold"),
            ("Dollar Strength", "fx", "Inverse relationship → bearish gold"),
            ("Dollar Weakness", "fx", "Inverse relationship → bullish gold"),
            ("Safe Haven Demand", "sentiment", "Crisis buying → bullish gold"),
            ("Risk-Off Environment", "sentiment", "Flight to quality → bullish gold"),
            ("Risk-On Environment", "sentiment", "Equities preferred → bearish gold"),
            ("Inflation Expectations Rising", "macro", "Gold as inflation hedge → bullish"),
            ("Fed Hawkishness", "policy", "Rate hike expectations → bearish gold"),
            ("Fed Dovishness", "policy", "Rate cut expectations → bullish gold"),
            ("Central Bank Buying", "flows", "Structural demand → bullish gold"),
            ("ETF Outflows", "flows", "Institutional selling → bearish gold"),
            ("ETF Inflows", "flows", "Institutional buying → bullish gold"),
            ("Geopolitical Crisis", "event", "Safe haven spike → bullish gold"),
            ("FOMC Surprise Hawk", "policy", "Unexpected hike/hawkish → sharp bearish gold"),
            ("FOMC Surprise Dove", "policy", "Unexpected cut/dovish → sharp bullish gold"),
            ("CPI Beat", "data", "Higher than expected inflation → complex, often bullish"),
            ("CPI Miss", "data", "Lower than expected inflation → complex, often bearish"),
            ("NFP Beat", "data", "Strong jobs = Fed stay higher → bearish gold"),
            ("NFP Miss", "data", "Weak jobs = Fed cut sooner → bullish gold"),
            ("Yield Curve Inversion", "macro", "Recession fear → safe haven bullish gold"),
            ("Technical Breakout Up", "technical", "Price above key resistance → momentum buy"),
            ("Technical Breakdown", "technical", "Price below key support → momentum sell"),
        ]
        
        with self.driver.session() as session:
            for name, category, description in concepts:
                session.run(
                    """MERGE (c:Concept {name: $name})
                       SET c.category = $category, c.description = $description""",
                    name=name, category=category, description=description
                )
    
    def ingest_economic_events(self, events: List) -> int:
        """Add economic events to graph."""
        count = 0
        with self.driver.session() as session:
            for event in events:
                session.run("""
                    MERGE (e:EconomicEvent {event_id: $event_id})
                    SET e.datetime_utc = $datetime_utc,
                        e.currency = $currency,
                        e.impact = $impact,
                        e.event_name = $event_name,
                        e.forecast = $forecast,
                        e.previous = $previous,
                        e.actual = $actual,
                        e.surprise_direction = $surprise_direction,
                        e.surprise_magnitude = $surprise_magnitude,
                        e.gold_relevance_score = $gold_relevance_score
                """, **event.dict())
                
                # Link to relevant concepts
                self._link_event_to_concepts(session, event)
                count += 1
        
        logger.info(f"Ingested {count} economic events")
        return count
    
    def _link_event_to_concepts(self, session, event):
        """Create edges between events and relevant concepts."""
        concept_map = {
            ("CPI", "beat"): "CPI Beat",
            ("CPI", "miss"): "CPI Miss",
            ("Non-Farm Payrolls", "beat"): "NFP Beat",
            ("Non-Farm Payrolls", "miss"): "NFP Miss",
            ("Federal Funds Rate", "beat"): "FOMC Surprise Hawk",
            ("Federal Funds Rate", "miss"): "FOMC Surprise Dove",
        }
        
        for (event_kw, surprise), concept_name in concept_map.items():
            if (event_kw.lower() in event.event_name.lower() and 
                    event.surprise_direction == surprise):
                session.run("""
                    MATCH (e:EconomicEvent {event_id: $eid})
                    MATCH (c:Concept {name: $concept})
                    MERGE (e)-[:TRIGGERS]->(c)
                """, eid=event.event_id, concept=concept_name)
    
    def ingest_fed_document(self, doc) -> str:
        """Add Fed document with embedding."""
        embedding = self.embedding_engine.embed(
            f"{doc.title} {doc.raw_text[:2000]}"
        )
        
        with self.driver.session() as session:
            session.run("""
                MERGE (d:Document {doc_id: $doc_id})
                SET d.doc_type = $doc_type,
                    d.speaker = $speaker,
                    d.title = $title,
                    d.date = $date,
                    d.url = $url,
                    d.raw_text = $raw_text,
                    d.sentiment_score = $sentiment_score,
                    d.gold_implication = $gold_implication,
                    d.embedding = $embedding
            """, **{**doc.dict(), "embedding": embedding})
            
            # Link to FedOfficial node
            session.run("""
                MERGE (f:FedOfficial {name: $speaker})
                WITH f
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (f)-[:AUTHORED]->(d)
            """, speaker=doc.speaker, doc_id=doc.doc_id)
            
            # Link concepts based on gold implication
            concept = {
                "hawkish": "Fed Hawkishness",
                "dovish": "Fed Dovishness"
            }.get(
                "hawkish" if doc.sentiment_score > 0.2 else 
                "dovish" if doc.sentiment_score < -0.2 else None
            )
            if concept:
                session.run("""
                    MATCH (d:Document {doc_id: $doc_id})
                    MATCH (c:Concept {name: $concept})
                    MERGE (d)-[:SUPPORTS]->(c)
                """, doc_id=doc.doc_id, concept=concept)
        
        return doc.doc_id
    
    def query_relevant_context(self, market_snapshot, top_k: int = 10) -> str:
        """
        GraphRAG: retrieve most relevant context for current market state.
        Returns a formatted string injected into each agent's prompt.
        """
        with self.driver.session() as session:
            # Get recent events and their gold impact
            recent_events = session.run("""
                MATCH (e:EconomicEvent)
                WHERE e.datetime_utc >= datetime() - duration('P7D')
                  AND e.gold_relevance_score >= 0.7
                RETURN e.event_name, e.surprise_direction, e.surprise_magnitude,
                       e.datetime_utc
                ORDER BY e.gold_relevance_score DESC
                LIMIT 5
            """).data()
            
            # Get active Fed signals
            fed_signals = session.run("""
                MATCH (f:FedOfficial)-[:AUTHORED]->(d:Document)
                WHERE d.date >= toString(date() - duration('P14D'))
                RETURN f.name, d.gold_implication, d.sentiment_score, d.title
                ORDER BY d.date DESC
                LIMIT 5
            """).data()
            
            # Get dominant concepts
            active_concepts = session.run("""
                MATCH (e:EconomicEvent)-[:TRIGGERS]->(c:Concept)
                WHERE e.datetime_utc >= datetime() - duration('P30D')
                WITH c, count(e) as frequency
                ORDER BY frequency DESC
                LIMIT 5
                RETURN c.name, c.description, frequency
            """).data()
        
        # Format into knowledge context string
        context_parts = ["=== KNOWLEDGE GRAPH CONTEXT ===\n"]
        
        if recent_events:
            context_parts.append("RECENT HIGH-IMPACT EVENTS:")
            for ev in recent_events:
                context_parts.append(
                    f"  • {ev['e.event_name']} | Surprise: {ev['e.surprise_direction']} "
                    f"({ev['e.surprise_magnitude']}%) | {ev['e.datetime_utc']}"
                )
        
        if fed_signals:
            context_parts.append("\nFED COMMUNICATIONS (last 14 days):")
            for sig in fed_signals:
                context_parts.append(
                    f"  • {sig['f.name']}: {sig['d.title']} → Gold: {sig['d.gold_implication']} "
                    f"(score: {sig['d.sentiment_score']:.2f})"
                )
        
        if active_concepts:
            context_parts.append("\nDOMINANT MARKET THEMES:")
            for c in active_concepts:
                context_parts.append(
                    f"  • {c['c.name']}: {c['c.description']}"
                )
        
        return "\n".join(context_parts)