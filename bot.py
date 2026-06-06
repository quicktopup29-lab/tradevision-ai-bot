import asyncio
from datetime import datetime
import os
import pandas as pd
import pytz
import requests
from telegram import Bot

# ================= CONFIG =================
TOKEN = "8967772189:AAG1mpGAOsFo2NbwK72t9UUbH-pD0nxLE0w"
CHANNEL_ID = "@tradevision_ai_signals"
API_KEY = "c1ec4ef642224321b031cf3068178289"

bot = Bot(token=TOKEN)

bd_tz = pytz.timezone("Asia/Dhaka")


# ================= SAFE API CALL =================
def safe_api_call(url, params):
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        if (
            data.get("code") == 429
            or data.get("status") == "error"
            or "values" not in data
        ):
            print(f"⛔ API LIMIT OR ERROR: {data.get('message', 'Rate Limit')}")
            return None

        return data

    except Exception as e:
        print(f"⚠️ API Connection Error: {e}")
        return None


# ================= MARKET DATA =================
def get_market_data(symbol):
    try:
        url = "https://api.twelvedata.com/time_series"

        params = {
            "symbol": symbol,
            "interval": "1min",
            "outputsize": 80,
            "apikey": API_KEY,
        }

        data = safe_api_call(url, params)

        if not data:
            return None

        df = pd.DataFrame(data["values"])

        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna()

        if len(df) < 55:
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
        rsi_val = 100 - (100 / (1 + rs))
        return rsi_val
    except:
        return pd.Series([50] * len(series))


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


# # ================= AI SIGNAL ENGINE (MORE SIGNALS MODE) =================
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

        # ট্রেন্ড কন্ডিশন একটু সহজ করা হলো
        trend_up = ema9.iloc[-1] > ema21.iloc[-1]
        trend_down = ema9.iloc[-1] < ema21.iloc[-1]

        score = 0

        if trend_up:
            score += 35
        if trend_down:
            score -= 35

        # RSI ফিল্টার একটু লুজ করা হলো যেন দ্রুত সিগন্যাল ধরে
        if rsi_val < 40:  # আগে ৩০ ছিল
            score += 25
        elif rsi_val > 60:  # আগে ৭০ ছিল
            score -= 25
        else:
            score += 10

        signal = None

        # স্কোর টার্গেট ৫০ থেকে কমিয়ে ৩০ করা হলো (তাড়াতাড়ি সিগন্যাল পাওয়ার জন্য)
        if score >= 30:
            signal = "BUY"
        elif score <= -30:
            signal = "SELL"

        if not signal:
            return None

        confidence = min(95, max(60, abs(score)))
        entry_time = datetime.now(bd_tz).strftime("%H:%M")

        direction_text = (
            "📈 Direction: BUY" if signal == "BUY" else "📉 Direction: SELL"
        )

        return f"""🔥 TRADEVISION AI VIP SIGNAL 🔥

━━━━━━━━━━━━━━━

💱 Pair: {symbol}
{direction_text}

⏰ Entry Time (BD 🇧🇩): {entry_time}
⌛ Expiry: 1 Minute

⚡ Confidence: {confidence:.0f}%

━━━━━━━━━━━━━━━

🚀 STATUS: ACTIVE
🤖 Powered by TradeVision AI"""

    except Exception as e:
        print("❌ Signal Error:", e)
        return None


        confidence = min(95, max(60, abs(score)))
        entry_time = datetime.now(bd_tz).strftime("%H:%M")

        direction_text = (
            "📈 Direction: BUY" if signal == "BUY" else "📉 Direction: SELL"
        )

        # আপনার দেওয়া হুবহু মেসেজ স্টাইল (ডাইনামিক ডেটা সহ)
        return f"""🔥 TRADEVISION AI VIP SIGNAL 🔥

━━━━━━━━━━━━━━━

💱 Pair: {symbol}
{direction_text}

⏰ Entry Time (BD 🇧🇩): {entry_time}
⌛ Expiry: 1 Minute

⚡ Confidence: {confidence:.0f}%

━━━━━━━━━━━━━━━

🚀 STATUS: ACTIVE
🤖 Powered by TradeVision AI"""

    except Exception as e:
        print("❌ Signal Error:", e)
        return None


# ================= MAIN LOOP =================
async def main():
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]

    print("🚀 TRADEVISION PRO STARTED...")

    while True:
        try:
            for pair in pairs:
                print(f"🔍 Checking {pair}...")

                signal = generate_signal(pair)

                if signal:
                    try:
                        await bot.send_message(chat_id=CHANNEL_ID, text=signal)
                        print(f"✅ SENT: {pair}")
                    except Exception as e:
                        print("❌ Telegram Error:", e)
                else:
                    print(f"⚠️ No Signal: {pair}")

                await asyncio.sleep(15)

            print("⏳ Waiting for next candle...\n")
            await asyncio.sleep(60)

        except Exception as e:
            print("🔥 MAIN LOOP ERROR:", e)
            await asyncio.sleep(30)


# ================= RUN =================
if __name__ == "__main__":
    asyncio.run(main())
