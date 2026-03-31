# Blue Guardian XAUUSD

A modular research and trading simulation framework for XAUUSD (Gold/USD) using knowledge graphs, agent-based modeling, and backtesting.

## Project Structure

- `config/` — Configuration files for agents, simulation, risk, and rules
- `data/` — Raw, processed, historical, and knowledge base data
- `src/` — Source code (ingestion, knowledge graph, agents, simulation, execution, utils)
- `scripts/` — Entrypoints and setup scripts
- `tests/` — Unit tests
- `notebooks/` — Jupyter notebooks for exploration and analysis
- `logs/` — Log files

## Quick Start

1. Copy `.env.example` to `.env` and fill in your keys
2. Build and start services:
   ```sh
   docker-compose up --build
   ```
3. Run the main script:
   ```sh
   python scripts/morning_run.py
   ```

## Requirements
See `requirements.txt`.
