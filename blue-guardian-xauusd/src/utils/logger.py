from loguru import logger
import sys

def setup_logger():
    logger.remove()
    logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
    logger.add("logs/blueguardian_{time:YYYY-MM-DD}.log", rotation="1 day")