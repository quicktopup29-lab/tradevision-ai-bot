import asyncio
import pandas as pd
import requests
from telegram import Bot  # অথবা আপনি যে লাইব্রেরি ব্যবহার করছেন (যেমন: aiogram)

API_KEY = "c1ec4ef642224321b031cf3068178289"
CHANNEL_ID = "@tradevision_ai_signals"  # আপনার চ্যানেল আইডি এখানে দিন
BOT_TOKEN = "8967772189:AAG1mpGAOsFo2NbwK72t9UUbH-pD0nxLE0w"  # আপনার বটের টোকেন এখানে দিন

# বট অবজেক্ট ইনিশিয়েট করা
bot = Bot(token=BOT_TOKEN)


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
            print("API ERROR:", data)
            return None

        df = pd.DataFrame(data["values"])

        # ডাটা টাইপ কনভার্ট করা
        df["close"] = df["close"].astype(float)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        return df[::-1]  # ডাটা রিভার্স করা (পুরোনো থেকে নতুন)

    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def generate_signal(symbol):
    df = get_market_data(symbol)

    if df is None or len(df) < 2:
        return None

    current = df["close"].iloc[-1]
    previous = df["close"].iloc[-2]

    # সহজ ট্রেন্ড অ্যানালাইসিস (আপনার লজিক অনুযায়ী)
    signal = "BUY" if current > previous else "SELL"

    # টেক প্রফিট এবং স্টপ লস ক্যালকুলেশন
    tp1 = round(current * 1.0005, 5)
    tp2 = round(current * 1.0010, 5)
    sl = round(current * 0.9990, 5)

    confidence = 80

    message = f"""
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
    return message


async def main():
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]

    # সব জোড়ার জন্য লুপ ঘুরিয়ে সিগন্যাল পাঠানো
    for pair in pairs:
        signal_text = generate_signal(pair)

        if signal_text:
            try:
                await bot.send_message(chat_id=CHANNEL_ID, text=signal_text)
                print(f"✅ Signal Sent: {pair}")
            except Exception as e:
                print(f"❌ Failed to send signal for {pair}: {e}")

        # প্রতিটি সিগন্যাল পাঠানোর মাঝে ৫ সেকেন্ডের বিরতি (এপিআই রেট লিমিট এড়াতে)
        await asyncio.sleep(5)


# স্ক্রিপ্টটি রান করার মূল অংশ
if __name__ == "__main__":
    asyncio.run(main())
