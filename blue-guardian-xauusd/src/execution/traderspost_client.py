# Placeholder for TradersPost client logic
# src/execution/traderspost_client.py
"""
TradersPost webhook client for semi-automated bridge to MT4/5.
IMPORTANT: This sends an ALERT only. Trader must manually confirm.
This maintains Blue Guardian compliance (no automated execution).
"""
import os
import json
import aiohttp
from loguru import logger


class TradersPostClient:
    """
    Sends trade alerts via TradersPost webhook.
    Flow: Python signal → TradersPost → MT4/5 EA (manual confirmation required).
    """
    
    def __init__(self):
        self.webhook_url = os.getenv("TRADERSPOST_WEBHOOK_URL")
        self.passphrase = os.getenv("TRADERSPOST_PASSPHRASE")
    
    async def send_alert(self, signal_payload: dict) -> bool:
        """
        Send trade alert to TradersPost.
        Returns True if successfully delivered.
        
        MT4 EA must have:
        - "Wait for Manual Confirmation" = TRUE
        - AlertsEnabled = TRUE
        This ensures MANUAL execution, not automated.
        """
        if not self.webhook_url:
            logger.warning("TradersPost webhook URL not configured")
            return False
        
        payload = {
            **signal_payload,
            "passphrase": self.passphrase,
            # CRITICAL: This flag prevents auto-execution
            "require_manual_confirmation": True,
            "source": "BlueGuardianAI"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        logger.success(f"✅ Alert sent to TradersPost: {payload['action'].upper()} {payload['ticker']}")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"TradersPost error {resp.status}: {body}")
                        return False
        except Exception as e:
            logger.error(f"TradersPost request failed: {e}")
            return False