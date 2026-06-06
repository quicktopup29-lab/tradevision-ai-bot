import asyncio
from datetime import datetime
import os
import time
import pandas as pd
import pytz
import requests
from telegram import Bot

# ================= CONFIG =================
API_KEY = "c1ec4ef642224321b031cf3068178289"
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHANNEL_ID = "YOUR_CHANNEL_ID"

bot = Bot(token=TELEGRAM_TOKEN)

bd_tz = pytz.timezone("Asia/Dhaka")


# ================= SAFE SYMBOL =================
def fix_symbol(symbol):
    return symbol.replace("/", "")


# ================= SAFE API CALL (UPDATED) =================
def safe_api_call(url, params):
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        # এপিআই রেট লিমিট হ্যান্ডেল করার জন্য পরিবর্তন
        if data.get("code") == 429:
            print("⛔ API LIMIT REACHED")
            return None

        return data

    except Exception as e:
        print(f"⚠️ API Error: {e}")
        return None


# ================= MARKET DATA =================
def get_market_data(symbol):
    try:
        url = "https://api.twelvedata.com/time_series"

        params = {
            "symbol": fix_symbol(symbol),
            "interval": "1min",
            "outputsize": 120,
            "apikey": API_KEY,
        }

        data = safe_api_call(url, params)

        if not data or "values" not in data:
            return None

        df = pd.DataFrame(data["values"])

        # SAFE CONVERT
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna()

        if len(df) < 50:
            return None

        return df[::-1]

    except Exception as e:
        print("❌ get_market_data error:", e)
        return None


# ================= INDICATORS =================
def rsi(series, period=14):
    try:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = -delta.where(delta < 0, 0).rolling(period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    except:
        return pd.Series([50] * len(series))


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


# ================= AI SIGNAL ENGINE =================
def generate_signal(symbol):
    df = get_market_data(symbol)

    if df is None:
        return None

    try:
        close = df["close"]

        ema9 = ema(close, 9)
        ema21 = ema(close, 21)
        ema50 = ema(close, 50)

        rsi_val = rsi(close).iloc[-1]
        price = close.iloc[-1]

        if pd.isna(rsi_val) or pd.isna(price):
            return None

        trend_up = ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1]
        trend_down = ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1]

        score = 0

        if trend_up:
            score += 40
        if trend_down:
            score -= 40

        if rsi_val < 30:
            score += 20
        elif rsi_val > 70:
            score -= 20
        else:
            score += 10

        volatility = close.pct_change().rolling(10).std().iloc[-1]

        if not pd.isna(volatility) and volatility < 0.002:
            score -= 10

        signal = None

        if score >= 50:
            signal = "BUY"
        elif score <= -50:
            signal = "SELL"

        if not signal:
            return None

        confidence = min(95, max(60, abs(score)))

        entry_time = datetime.now(bd_tz).strftime("%H:%M")

        tp1 = price * (1.0010 if signal == "BUY" else 0.9990)
        tp2 = price * (1.0020 if signal == "BUY" else 0.9980)
        sl = price * (0.9990 if signal == "BUY" else 1.0010)

        return f"""
🤖 CRASH PROOF AI ENGINE

💱 Pair: {symbol}
📊 Signal: {signal}

⏰ Entry Time (BD 🇧🇩): {entry_time}
⏳ Expiry: 1 Minute

💰 Price: {price:.5f}
📈 RSI: {rsi_val:.2f}
🧠 AI Score: {score}
⚡ Confidence: {confidence:.1f}%

🎯 TP1: {tp1:.5f}
🎯 TP2: {tp2:.5f}
🛑 SL: {sl:.5f}

🔥 STATUS: SAFE MODE ACTIVE
"""

    except Exception as e:
        print("❌ Signal Error:", e)
        return None


# ================= MAIN LOOP (CRASH SAFE) =================
async def main():
    # ফ্রি প্ল্যানের জন্য শুধুমাত্র ২টি পেয়ার রাখা হলো
    pairs = ["EUR/USD", "GBP/USD"]

    print("🚀 CRASH PROOF ENGINE STARTED...")

    while True:
        try:
            for pair in pairs:
                print(f"🔍 Checking {pair}...")

                signal = generate_signal(pair)

                if signal:
                    try:
                        await bot.send_message(chat_id=CHANNEL_ID, text=signal)
                        print(f"✅ SENT: {pair}")
                        await asyncio.sleep(5)
                    except Exception as e:
                        print("❌ Telegram Error:", e)
                else:
                    print(f"⚠️ No signal: {pair}")

                # প্রতিটি পেয়ার চেকের মাঝে বিরতি বাড়িয়ে ১৫ সেকেন্ড করা হলো
                await asyncio.sleep(15)

            # পুরো সাইকেল শেষে ৬০ সেকেন্ডের বিরতি
            print("⏳ Cycle complete, waiting 60s...\n")
            await asyncio.sleep(60)

        except Exception as e:
            print("🔥 MAIN LOOP CRASH PREVENTED:", e)
            await asyncio.sleep(10)


# ================= RUN =================
if __name__ == "__main__":
    asyncio.run(main())
