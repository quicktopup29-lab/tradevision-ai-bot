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
# আপনার টেলিগ্রাম চ্যানেলের ID বা ইউজারনেম (যেমন: "@my_channel_username" অথবা -100123456789)
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID") 

# ১. মার্কেট ডেটা সংগ্রহের ফাংশন (Forex API)
def get_market_data(symbol="EUR/USD, GBP/USD, USD/JPY", interval="1h", limit=100):
    url = f"url = "https://www.alphavantage.co/query""
    {
  "Time Series FX (1min)": {
    "2026-06-05 17:00:00": {
      "1. open": "...",
      "2. high": "...",
      "3. low": "...",
      "4. close": "..."
    }
  }
}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None
    
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    return df

# ২. RSI/EMA/MACD গণনার লজিক এবং বাজার পরিস্থিতি বিশ্লেষণ
def analyze_indicators(df):
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
async def send_automatic_update(bot: Bot, symbol="EURUSD
GBPUSD
USDJPY
AUDUSD"):
    print(f"⏳ {symbol} এর ডেটা বিশ্লেষণ করে চ্যানেলে পাঠানো হচ্ছে...")
    df = get_market_data(symbol=symbol)
    if df is None:
        print("❌ ডেটা সংগ্রহ করা যায়নি।")
        return
        
    analysis = analyze_indicators(df)
    
    message = (
        f"📢 **Automated Market Update: {symbol.upper()}**\n"
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
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="Markdown")
        print("✅ চ্যানেলে সফলভাবে পোস্ট করা হয়েছে।")
    except Exception as e:
        print(f"❌ চ্যানেলে পোস্ট করতে সমস্যা হয়েছে: {e}")

# ৪. নির্দিষ্ট সময় পর পর লুপ চালানোর মেইন ফাংশন
async def main():
    if not TOKEN or not CHANNEL_ID:
        print("Error: TELEGRAM_BOT_TOKEN বা TELEGRAM_CHANNEL_ID পাওয়া যায়নি!")
        return

    bot = Bot(token=TOKEN)
    print("Auto-posting bot is running...")
    
    # অনন্তকাল ধরে লুপ চলবে
    while True:
        # এখানে আপনি যে কয়টি পেয়ারের আপডেট চান তা যুক্ত করতে পারেন
        symbols_to_track = ["BTCUSDT", "ETHUSDT"]
        
        for symbol in symbols_to_track:
            await send_automatic_update(bot, symbol=symbol)
            await asyncio.sleep(2) # দুটি পেয়ারের মাঝে ২ সেকেন্ড গ্যাপ
            
        # প্রতি ১ ঘণ্টা (৩৬০০ সেকেন্ড) পর পর আপডেট পাঠাবে
        # পরীক্ষার জন্য আপনি এখানে ৬০ দিয়ে ১ মিনিট পর পর চেক করতে পারেন
        print("😴 পরবর্তী আপডেটের জন্য ১ ঘণ্টা অপেক্ষা করা হচ্ছে...")
        await asyncio.sleep(3600) 

if __name__ == "__main__":
    # অসিঙ্ক্রোনাস মেইন লুপ রান করা
    asyncio.run(main())