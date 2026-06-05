import os
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Local testing এর জন্য .env ফাইল লোড করবে
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ১. মার্কেট ডেটা সংগ্রহের ফাংশন (Binance API)
def get_market_data(symbol="BTCUSDT", interval="1h", limit=100):
    url = f"https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None
    
    data = response.json()
    # ওয়ান-লাইন ডেটা ফ্রেম তৈরি
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    return df

# ২. RSI/EMA/MACD গণনার লজিক
def analyze_indicators(df):
    # RSI (Period: 14)
    rsi_series = RSIIndicator(close=df['close'], window=14).rsi()
    
    # EMA (Period: 20)
    ema_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
    
    # MACD (Fast: 12, Slow: 26, Signal: 9)
    macd_init = MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
    macd_series = macd_init.macd()
    macd_signal_series = macd_init.macd_signal()
    
    # সর্বশেষ (Current) ভ্যালু নেওয়া
    analysis = {
        "current_price": df['close'].iloc[-1],
        "rsi": round(rsi_series.iloc[-1], 2),
        "ema": round(ema_series.iloc[-1], 2),
        "macd": round(macd_series.iloc[-1], 2),
        "macd_signal": round(macd_signal_series.iloc[-1], 2)
    }
    return analysis

# ৩. টেলিগ্রাম কমান্ড হ্যান্ডলার
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("স্বাগতম! মার্কেট অ্যানালাইসিস দেখতে টাইপ করুন: /analyze BTCUSDT")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ডিফল্ট সিম্বল BTCUSDT, ইউজার চাইলে অন্যটাও দিতে পারবে
    symbol = context.args[0] if context.args else "BTCUSDT"
    await update.message.reply_text(f"⏳ {symbol}-এর ডেটা বিশ্লেষণ করা হচ্ছে...")
    
    df = get_market_data(symbol=symbol)
    if df is None:
        await update.message.reply_text("❌ ডেটা সংগ্রহ করা যায়নি। দয়া করে সঠিক সিম্বল দিন (যেমন: ETHUSDT)।")
        return
        
    analysis = analyze_indicators(df)
    
    # ইউজার ইন্টারফেস মেসেজ ফরম্যাট (কোনো সিগন্যাল ছাড়া শুধু ডেটা)
    message = (
        f"📊 **Market Analysis For {symbol.upper()}**\n"
        f"---"
        f"💰 Current Price: ${analysis['current_price']}\n"
        f"📈 RSI (14): {analysis['rsi']}\n"
        f"📉 EMA (20): ${analysis['ema']}\n"
        f"🔄 MACD Line: {analysis['macd']}\n"
        f"🎯 MACD Signal: {analysis['macd_signal']}\n"
        f"---"
        f"*দ্রষ্টব্য: এটি কোনো আর্থিক পরামর্শ বা ট্রেডিং সিগন্যাল নয়।*"
    )
    await update.message.reply_text(message, parse_mode="Markdown")

# ৪. মেইন ড্রাইভ
def main():
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN পাওয়া যায়নি!")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
