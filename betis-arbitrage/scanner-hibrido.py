"""
ARBITRAGE SCANNER - HÍBRIDO
Betfair API (GRATIS) + 1xBet + 888sport (scraping inteligente)

Requirements:
    pip install -r requirements.txt

Setup Betfair:
    1. Crea cuenta: https://www.betfair.com/
    2. API Key: https://developer.betfair.com/
    3. Edita .env con USERNAME, PASSWORD, API_KEY
"""

import requests
from bs4 import BeautifulSoup
import cloudscraper
import json
from datetime import datetime, timezone
import time
import re
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

# BETFAIR (desde .env)
BETFAIR_USERNAME = os.getenv('BETFAIR_USERNAME', 'tu_email@betfair.com')
BETFAIR_PASSWORD = os.getenv('BETFAIR_PASSWORD', 'tu_contraseña')
BETFAIR_API_KEY = os.getenv('BETFAIR_API_KEY', 'tu_api_key')

# ARBITRAJE
CAPITAL_TOTAL = 100.0
MIN_PROFIT_PERCENT = 2.0
MAX_MARGIN = 0.98
MIN_ODDS = 1.01
MAX_ODDS = 50.0

BETFAIR_API = "https://api.betfair.com/exchange/betting/json-rpc/v1"
LOGIN_API = "https://identitysso.betfair.com/api/login"

# URLs
URLS = {
    '1xbet': 'https://1xbet.com/en/line/',
    '888sport': 'https://www.888sport.com/'
}

session_token = None
scraper = cloudscraper.create_scraper()


# ============================================================================
# BETFAIR API
# ============================================================================

def login_betfair():
    """Autentica con Betfair."""
    global session_token

    print("🔐 Autenticando Betfair...")

    try:
        response = requests.post(
            LOGIN_API,
            json={
                'username': BETFAIR_USERNAME,
                'password': BETFAIR_PASSWORD
            },
            headers={'X-Application': BETFAIR_API_KEY}
        )

        if response.status_code == 200:
            data = response.json()
            session_token = data.get('sessionToken')
            if session_token:
                print("✅ Betfair autenticado")
                return True

        print("❌ Error Betfair")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "=" * 120)
    print("🎲 ARBITRAGE SCANNER - BETFAIR + 1XBET + 888SPORT")
    print("100% GRATIS | Tiempo Real | Múltiples Casas")
    print("=" * 120 + "\n")

    if not login_betfair():
        print("⚠️  Betfair no disponible, continuando solo con scraping...")


if __name__ == "__main__":
    main()