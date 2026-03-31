# scripts/setup_neo4j.py
import os
from src.knowledge_graph.graph_builder import XAUUSDGraphBuilder

if __name__ == "__main__":
    graph = XAUUSDGraphBuilder(
        uri=os.getenv("NEO4J_URI"),
        user=os.getenv("NEO4J_USER"),
        password=os.getenv("NEO4J_PASSWORD")
    )
    graph.initialize_schema()
    print("✅ Neo4j schema initialized and core concepts seeded.")