import asyncio
import requests
import pandas as pd
from datetime import datetime
import pytz
from telegram import Bot

# ================= CONFIG =================
API_KEY = "YOUR_TWELVEDATA_API_KEY"
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHANNEL_ID = "YOUR_CHANNEL_ID"

bot = Bot(token=TELEGRAM_TOKEN)

# ================= TIMEZONE =================
bd_tz = pytz.timezone("Asia/Dhaka")


# ================= SYMBOL FIX =================
def fix_symbol(symbol):
    return symbol.replace("/", "")


# ================= MARKET DATA =================
def get_market_data(symbol="EUR/USD"):
    try:
        url = "https://api.twelvedata.com/time_series"

        clean_symbol = fix_symbol(symbol)

        params = {
            "symbol": clean_symbol,
            "interval": "1min",
            "outputsize": 120,
            "apikey": API_KEY
        }

        response = requests.get(url, params=params)
        data = response.json()

        if "values" not in data:
            print("❌ API ERROR:", data)
            return None

        df = pd.DataFrame(data["values"])
        df = df.astype({"close": float})

        return df[::-1]

    except Exception as e:
        print("❌ ERROR:", e)
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

    # ===== PRO LOGIC =====
    if trend_up and rsi_val < 70:
        signal = "BUY"
        confidence = 80 + (70 - rsi_val) * 0.5

    elif trend_down and rsi_val > 30:
        signal = "SELL"
        confidence = 80 + (rsi_val - 30) * 0.5

    if not signal:
        return None

    entry_time = datetime.now(bd_tz).strftime("%H:%M")

    return f"""
🔥 PRO TRADING ENGINE SIGNAL

💱 Pair: {symbol}
📊 Signal: {signal}

⏰ Entry Time (BD 🇧🇩): {entry_time}
⏳ Expiry: 1 Minute

💰 Price: {price:.5f}
📈 RSI: {rsi_val:.2f}
⚡ Confidence: {confidence:.1f}%

🚀 STATUS: LIVE MARKET ANALYSIS
"""


# ================= MAIN LOOP =================
async def main():
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]

    print("🚀 PRO TRADING ENGINE STARTED...")

    while True:
        for pair in pairs:
            print(f"🔍 Scanning {pair}...")

            signal = generate_signal(pair)

            if signal:
                try:
                    await bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=signal
                    )
                    print(f"✅ SENT SIGNAL: {pair}")

                except Exception as e:
                    print("❌ TELEGRAM ERROR:", e)

            await asyncio.sleep(5)

        print("⏳ Waiting next 1-minute cycle...")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())