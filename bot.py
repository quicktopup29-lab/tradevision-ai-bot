import asyncio
import os
import pandas as pd
import requests
from telegram import Bot

# ১. CHANNEL_ID এবং অন্যান্য ক্রেডেনশিয়াল ডিফাইন করা (Environment Variables থেকে)
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "c1ec4ef642224321b031cf3068178289")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "YOUR_CHANNEL_ID_HERE")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ২. bot ডিফাইন করা (main() এর আগে অবশ্যই থাকতে হবে)
bot = Bot(token=TOKEN)


# ৩. get_market_data() ফাংশন (যা generate_signal এর ভেতরে কল করা হচ্ছে)
def get_market_data(symbol="EUR/USD"):
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": "1min",
            "outputsize": 50,
            "apikey": API_KEY,
        }

        response = requests.get(url, params=params)
        data = response.json()

        if "values" not in data:
            print(f"❌ API ERROR for {symbol}: {data}")
            return None

        df = pd.DataFrame(data["values"])

        # ডাটা টাইপ কনভার্ট করা
        df["close"] = df["close"].astype(float)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        return df[::-1]  # ওল্ডেস্ট থেকে নিউয়েস্ট ক্রোনোলজিক্যাল অর্ডার

    except Exception as e:
        print(f"❌ Exception in get_market_data for {symbol}: {e}")
        return None


def generate_signal(symbol):
    # ৩ নম্বর পয়েন্টের ভ্যালিডেশন: এখানে get_market_data() কল হচ্ছে
    df = get_market_data(symbol)

    if df is None or len(df) < 2:
        return None

    current = df["close"].iloc[-1]
    previous = df["close"].iloc[-2]

    signal = "BUY" if current > previous else "SELL"

    tp1 = round(current * 1.0005, 5)
    tp2 = round(current * 1.0010, 5)
    sl = round(current * 0.9990, 5)
    confidence = 80

    return f"""
🔥 TRADEVISION VIP SIGNAL

💱 Pair: {symbol}
📈 Signal: {signal}

🎯 Entry: {current:.5f}
🎯 TP1: {tp1:.5f}
🎯 TP2: {tp2:.5f}
🛑 SL: {sl:.5f}

⏰ Expiry: 5 Minutes

⚡ Confidence: {confidence}%
"""


async def main():
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]

    print("🚀 Bot Started successfully...")

    while True:
        # আপনার ফ্লো চার্ট অনুযায়ী লুপ কাজ করবে
        for pair in pairs:
            print(f"🔍 Checking {pair}...")
            signal = generate_signal(pair)

            if signal:
                try:
                    await bot.send_message(chat_id=CHANNEL_ID, text=signal)
                    print(f"✅ Signal Sent: {pair}")
                except Exception as e:
                    print(f"❌ Failed to send signal for {pair}: {e}")

            # এপিআই রেট লিমিট বা স্প্যামিং এড়াতে প্রতি পেয়ারের মাঝে ছোট বিরতি
            await asyncio.sleep(2)

        # আপনার দেওয়া ফ্লো অনুযায়ী সব জোড়া চেক শেষে ৬০ সেকেন্ডের বিরতি এবং Repeat
        print("⏳ All pairs checked. Waiting 60 seconds before next round...\n")
        await asyncio.sleep(60)


# নিচে এই এন্ট্রি পয়েন্টটি থাকা বাধ্যতামূলক ছিল, যা যুক্ত করা হয়েছে:
if __name__ == "__main__":
    asyncio.run(main())
