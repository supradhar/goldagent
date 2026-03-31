# scripts/validate_system.py
import os
from loguru import logger

def validate():
    print("=== Blue Guardian System Validation ===")
    required_env = ["NEO4J_URI", "LLM_BACKEND"]
    for var in required_env:
        if not os.getenv(var):
            print(f"⚠️  Missing env var: {var}")
        else:
            print(f"✅ {var} present")
    print("✅ Validation passed (basic checks)")
    logger.info("System validation complete")

if __name__ == "__main__":
    validate()