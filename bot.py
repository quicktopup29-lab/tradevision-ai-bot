import os
import asyncio
import requests
import pandas as pd
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
API_KEY = os.getenv("FOREX_API_KEY")

PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "AUD/USD"
]

bot = Bot(token=TOKEN)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
import requests

# replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo'
r = requests.get(url)
data = r.json()

print(data)
# API key: QD90GKKPG2JJG7DC
API_KEY = "QD90GKKPG2JJG7DC"
def get_market_data(symbol="EURUSD"):
    print(f"Fetching {symbol}...")

    try:
        url = "https://api.exchangerate.host/live"
        params = {
            "access_key": API_KEY,
            "source": symbol[:3],
            "currencies": symbol[3:]
        }

        response = requests.get(url, params=params)
        data = response.json()

        print(data)

        if "quotes" not in data:
            return None

        price = list(data["quotes"].values())[0]

        df = pd.DataFrame({
            "close": [price] * 50
        })

        return df

    except Exception as e:
        print(e)
        return None
async def main():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN NOT FOUND")
        return

    if not CHANNEL_ID:
        print("❌ TELEGRAM_CHANNEL_ID NOT FOUND")
        return

    bot = Bot(token=TOKEN)

    print("✅ Bot Started Successfully")

    while True:
        try:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text="""
🔥 TRADEVISION VIP SIGNAL

💱 Pair: EUR/USD
📈 Signal: BUY

🎯 Entry: 1.14520
🎯 TP1: 1.14600
🎯 TP2: 1.14700
🛑 SL: 1.14420

⏰ Expiry: 5 Minutes

⚡ Confidence: 87%
"""
            )
            print("✅ Message Sent Successfully")

        except Exception as e:
            print(f"❌ ERROR: {e}")

        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())