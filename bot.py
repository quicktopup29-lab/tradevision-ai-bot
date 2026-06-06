import os
import asyncio
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from telegram import Bot
from dotenv import load_dotenv

# Local testing এর জন্য .env ফাইল লোড করবে
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID") 
API_KEY = os.getenv("FOREX_API_KEY")

# ১. মার্কেট ডেটা সংগ্রহের ফাংশন
def get_market_data(symbol="EURUSD"):
    print("FUNCTION RUNNING:", symbol)
    print("API_KEY =", API_KEY)

    url = "https://www.alphavantage.co/query"

    params = {
        "function": "FX_INTRADAY",
        "from_symbol": symbol[:3],
        "to_symbol": symbol[3:],
        "interval": "1min",
        "outputsize": "compact",
        "apikey": API_KEY
    }

    try:
        response = requests.get(url, params=params)

        print("STATUS =", response.status_code)

        if response.status_code != 200:
            return None
print("API KEY =", API_KEY)

response = requests.get(url, params=params)

print("STATUS =", response.status_code)
print("TEXT =", response.text[:500])
        data = response.json()
     print(data)
        if "Time Series FX (1min)" not in data:
            if "Note" in data:
                print("API LIMIT:", data["Note"])
            return None

        ts = data["Time Series FX (1min)"]

        rows = []

        for time_key, values in ts.items():
            rows.append({
                "timestamp": time_key,
                "close": float(values["4. close"])
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("timestamp")
        df = df.reset_index(drop=True)

        return df

    except Exception as e:
        print(f"❌ Error fetching data for {symbol}: {e}")
        return None
# ২. RSI/EMA/MACD গণনার লজিক এবং বাজার পরিস্থিতি विश्लेषण
def analyze_indicators(df):
    # আপনার দেওয়া নতুন কন্ডিশন: পর্যাপ্ত ডেটা না থাকলে None ব্যাক করবে
    if len(df) < 35:
        return None

    close_prices = df['close']
    current_price = close_prices.iloc[-1]
    
    # RSI (Period: 14)
    rsi_series = RSIIndicator(close=close_prices, window=14).rsi()
    current_rsi = round(rsi_series.iloc[-1], 2)
    
    if current_rsi >= 70:
        rsi_status = "Overbought (অতিরিক্ত ক্রয়)"
    elif current_rsi <= 30:
        rsi_status = "Oversold (অতিরিক্ত বিক্রয়)"
    else:
        rsi_status = "Neutral (স্বাভাবিক)"
        
    # EMA (Period: 20)
    ema_series = EMAIndicator(close=close_prices, window=20).ema_indicator()
    current_ema = round(ema_series.iloc[-1], 2)
    
    if current_price > current_ema:
        ema_status = "Above EMA (ঊর্ধ্বমুখী প্রবণতা)"
    else:
        ema_status = "Below EMA (নিম্নমুখী প্রবণতা)"
    
    # MACD (Fast: 12, Slow: 26, Signal: 9)
    macd_init = MACD(close=close_prices, window_fast=12, window_slow=26, window_sign=9)
    current_macd = round(macd_init.macd().iloc[-1], 2)
    current_signal = round(macd_init.macd_signal().iloc[-1], 2)
    
    if current_macd > current_signal:
        macd_status = "Bullish Crossover (পজিティブ মোমেন্টাম)"
    else:
        macd_status = "Bearish Crossover (নেগেティブ মোমেন্টাম)"
    
    return {
        "current_price": current_price,
        "rsi": current_rsi,
        "rsi_status": rsi_status,
        "ema": current_ema,
        "ema_status": ema_status,
        "macd": current_macd,
        "macd_signal": current_signal,
        "macd_status": macd_status
    }

# ৩. চ্যানেলে অটোমেটিক মেসেজ পাঠানোর ফাংশন
async def send_automatic_update(bot: Bot, symbol="EURUSD"):
    print(f"⏳ {symbol} এর ডেটা বিশ্লেষণ করে চ্যানেলে পাঠানো হচ্ছে...")
    df = get_market_data(symbol=symbol)
    if df is None or df.empty:
        print(f"❌ {symbol} এর ডেটা সংগ্রহ করা যায়নি বা ডেটা খালি।")
        return
        
    # আপনার দেওয়া নতুন কন্ডিশন এখানে সেট করা হয়েছে
    analysis = analyze_indicators(df)
    if analysis is None:
        print(f"⚠️ {symbol} এর পর্যাপ্ত ডেটা (কমপক্ষে ৩৫টি রো) না থাকায় স্কিপ করা হলো।")
        return
    
    message = (
        f"📊 TRADEVISION MARKET UPDATE\n\n"
        f"💱 Pair: {symbol}\n\n"
        f"💰 Current Price: {analysis['current_price']}\n\n"
        f"📈 RSI (14): {analysis['rsi']}\n"
        f"📊 RSI Status: {analysis['rsi_status']}\n\n"
        f"📉 EMA Trend: {analysis['ema_status']}\n\n"
        f"🔄 MACD Trend: {analysis['macd_status']}\n\n"
        f"⏰ Auto Updated"
    )
    
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=message)
        print(f"✅ {symbol} সফলভাবে চ্যানেলে পোস্ট করা হয়েছে।")
    except Exception as e:
        print(f"❌ চ্যানেলে পোস্ট করতে সমস্যা হয়েছে: {e}")

# ৪. মেইন ফাংশন
async def main():
    print("API KEY =", API_KEY)

    if not TOKEN or not CHANNEL_ID:
        print("Error: TELEGRAM_BOT_TOKEN বা TELEGRAM_CHANNEL_ID পাওয়া যায়নি!")
        return
    bot = Bot(token=TOKEN)

await bot.send_message(

    chat_id=CHANNEL_ID,

    text="✅ TradeVision Bot Online"

)

    print("Auto-posting bot is running...")
    
    while True:
        symbols_to_track = [
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "AUDUSD"
        ]
        
        for symbol in symbols_to_track:
            await send_automatic_update(bot, symbol=symbol)
            await asyncio.sleep(2) # পেয়ারগুলোর মাঝে ২ সেকেন্ডের গ্যাপ
            
        print("TEST MESSAGE SENT")
        await asyncio.sleep(3600) # ১ ঘণ্টা পর পর লুপ চলবে

if __name__ == "__main__":
    asyncio.run(main())
