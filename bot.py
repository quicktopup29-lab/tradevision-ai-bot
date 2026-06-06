import asyncio
import requests
import pandas as pd
from datetime import datetime
import pytz
from telegram import Bot

# ================= CONFIG =================
API_KEY = "c1ec4ef642224321b031cf3068178289"
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHANNEL_ID = "YOUR_CHANNEL_ID"

bot = Bot(token=TELEGRAM_TOKEN)

# ================= TIMEZONE (BD GMT+6) =================
bd_tz = pytz.timezone("Asia/Dhaka")


# ================= MARKET DATA =================
def get_market_data(symbol="EUR/USD"):
    try:
        url = "https://api.twelvedata.com/time_series"

        params = {
            "symbol": symbol,
            "interval": "1min",
            "outputsize": 120,
            "apikey": API_KEY
        }

        r = requests.get(url, params=params)
        data = r.json()

        if "values" not in data:
            return None

        df = pd.DataFrame(data["values"])
        df = df.astype({"close": float})

        return df[::-1]

    except:
        return None


# ================= RSI =================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()

    rs = gain / loss
    return 100 - (100 / (1 + rs))


# ================= SIGNAL ENGINE =================
def generate_signal(symbol):
    df = get_market_data(symbol)

    if df is None or len(df) < 50:
        return None

    close = df["close"]

    ema9 = close.ewm(span=9).mean()
    ema21 = close.ewm(span=21).mean()
    ema50 = close.ewm(span=50).mean()

    rsi_val = rsi(close).iloc[-1]
    price = close.iloc[-1]

    trend_up = ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1]
    trend_down = ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1]

    signal = None
    confidence = 50

    # ===== SMART LOGIC =====
    if trend_up and 40 < rsi_val < 70:
        signal = "BUY"
        confidence = 85 + (70 - rsi_val) * 0.3

    elif trend_down and 30 < rsi_val < 60:
        signal = "SELL"
        confidence = 85 + (rsi_val - 30) * 0.3

    if not signal:
        return None

    entry_time = datetime.now(bd_tz).strftime("%H:%M")

    return f"""
🔥 TRADEVISION ULTIMATE AI SIGNAL

💱 Pair: {symbol}
📉 Signal: {signal}

⏰ Entry Time (BD 🇧🇩): {entry_time}
⏳ Expiry: 1 Minute

📊 Price: {price:.5f}
📈 RSI: {rsi_val:.2f}
⚡ Confidence: {confidence:.1f}%

🇧🇩 Timezone: GMT+6 (Bangladesh)

🚀 ULTIMATE AI SYSTEM
"""


# ================= MAIN LOOP =================
async def main():
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]

    print("🚀 ULTIMATE TRADEVISION BOT STARTED...")

    while True:
        for pair in pairs:
            print(f"🔍 Analyzing {pair}...")

            signal = generate_signal(pair)

            if signal:
                try:
                    await bot.send_message(chat_id=CHANNEL_ID, text=signal)
                    print(f"✅ SENT: {pair}")

                except Exception as e:
                    print("❌ ERROR:", e)

            await asyncio.sleep(7)

        print("⏳ Next cycle in 60 seconds...")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())