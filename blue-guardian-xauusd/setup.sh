#!/bin/bash
# Setup script for Blue Guardian XAUUSD
set -e

echo "=== Blue Guardian XAUUSD System Setup ==="

# 1. Copy env
cp .env.example .env
echo "► Edit .env with your API keys before continuing"

# 2. Start infrastructure
docker-compose up -d neo4j zep redis
sleep 15  # Wait for Neo4j to initialize

# 3. Install Python deps
pip install -r requirements.txt

# 4. Pull Ollama models (local version only)
if [ "$LLM_BACKEND" = "ollama" ]; then
	docker exec bg_ollama ollama pull llama3.1:70b
	docker exec bg_ollama ollama pull nomic-embed-text
fi

# 5. Initialize Neo4j schema
python scripts/setup_neo4j.py

# 6. Validate system
python scripts/validate_system.py

echo "=== Setup Complete ==="
#!/bin/bash
# Setup script for Blue Guardian XAUUSD
cp .env.example .env
pip install -r requirements.txt
