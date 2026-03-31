import os
from loguru import logger

def validate():
    print("=== Blue Guardian System Validation ===")
    required = ["NEO4J_URI", "LLM_BACKEND"]
    for v in required:
        print(f"✅ {v} present" if os.getenv(v) else f"⚠️  Missing {v}")
    logger.info("System validation complete")

if __name__ == "__main__":
    validate()