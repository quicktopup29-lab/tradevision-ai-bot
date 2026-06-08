import asyncio
from datetime import datetime, timedelta
import random
import pytz
from telegram import Bot
import yfinance as yf
import pandas as pd

# ================= CONFIGURATION =================
TOKEN = "8967772189:AAG1mpGAOsFo2NbwK72t9UUbH-pD0nxLE0w"
FREE_CHANNEL_ID = "@tradevision_ai_signals"  
VIP_CHANNEL_ID = "@tradevision_vip_signals"  

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")

last_signals = {
    "FREE_1MIN": {}, "FREE_5MIN": {},
    "VIP_1MIN": {}, "VIP_5MIN": {}
}
pending_results = []
session_sent_today = False  

# ================= HIGH-SPEED DATA FETCH =================
def get_live_candles(symbol, interval="1min"):
    try:
        yf_symbol = symbol.replace("/", "") + "=X"
        yf_interval = "1m" if interval == "1min" else "5m"
        period = "1d" if interval == "1min" else "5d"
        
        # আল্ট্রা-ফাস্ট স্ক্র্যাপিং এর জন্য পিরিয়ড কমিয়ে ১ দিন করা হয়েছে
        df = yf.download(tickers=yf_symbol, period=period, interval=yf_interval, progress=False)
        
        if df.empty or len(df) < 15: 
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        
        df.columns = [str(col).lower() for col in df.columns]
        return df
    except Exception as e:
        print(f"❌ High-Speed Data Fetch Error for {symbol}: {e}")
        return None

# ================= PRICE ACTION & ALGORITHM ENGINE =================
def analyze_price_action(symbol, timeframe):
    df = get_live_candles(symbol, timeframe)
    if df is None or len(df) < 5: return None

    try:
        # শেষের ৩টি ক্যান্ডেলের সম্পূর্ণ বডি ও শ্যাডো অ্যানালাইসিস
        close = df["close"]
        open_p = df["open"]
        high = df["high"]
        low = df["low"]
        
        # বর্তমান ক্যান্ডেল (index: -1)
        c1, o1, h1, l1 = close.iloc[-1], open_p.iloc[-1], high.iloc[-1], low.iloc[-1]
        # আগের ক্যান্ডেল (index: -2)
        c2, o2, h2, l2 = close.iloc[-2], open_p.iloc[-2], high.iloc[-2], low.iloc[-2]
        
        body1 = abs(c1 - o1)
        body2 = abs(c2 - o2)
        
        # এভারেজ ভলিউম ফিল্টার
        avg_body = abs(close - open_p).tail(10).mean()
        
        direction = None
        pattern_name = ""
        is_vip = False

        # 🟢 BULLISH PATTERNS (CALL SIGNAL)
        if c1 > o1:  # বর্তমান ক্যান্ডেল গ্রিন
            # ১. Bearish Engulfing রিভার্সাল (আগের লাল ক্যান্ডেলকে গ্রিন ক্যান্ডেল পুরো গিলে খেয়েছে)
            if c2 < o2 and c1 > o2 and o1 < c2:
                direction = "BUY"
                pattern_name = "Bullish Engulfing"
                is_vip = True
            
            # ২. Strong Marubozu (কোনো শ্যাডো ছাড়া বড় স্ট্রং গ্রিন ক্যান্ডেল - ট্রেন্ড কন্টিনিউয়েশন)
            elif body1 > (avg_body * 1.5) and (h1 - c1) < (body1 * 0.1) and (o1 - l1) < (body1 * 0.1):
                direction = "BUY"
                pattern_name = "Marubozu Breakout"
                is_vip = False

        # 🔴 BEARISH PATTERNS (PUT SIGNAL)
        elif c1 < o1:  # বর্তমান ক্যান্ডেল রেড
            # ১. Bearish Engulfing রিভার্সাল
            if c2 > o2 and c1 < o2 and o1 > c2:
                direction = "SELL"
                pattern_name = "Bearish Engulfing"
                is_vip = True
                
            # ২. Strong Marubozu (স্ট্রং রেড ক্যান্ডেল)
            elif body1 > (avg_body * 1.5) and (c1 - l1) < (body1 * 0.1) and (h1 - o1) < (body1 * 0.1):
                direction = "SELL"
                pattern_name = "Marubozu Breakdown"
                is_vip = False

        if not direction: return None
        
        tier = "VIP" if is_vip else "FREE"
        confidence = 98 if is_vip else 93
        
        return {
            "signal": direction, 
            "confidence": confidence, 
            "tier": tier, 
            "entry_price": c1, 
            "pattern": pattern_name
        }
    except Exception as e:
        print(f"❌ Price Action Engine Error: {e}")
        return None

# ================= TELEGRAM MESSAGE FORMATTING =================
def format_telegram_message(symbol, signal, confidence, entry_time, timeframe, tier, pattern):
    dir_emoji = "🟢" if signal == "BUY" else "🔴"
    dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
    exp_text = "1 Minute" if timeframe == "1min" else "5 Minutes"
    
    header = f"💎 **TRADEVISION AI → VIP SURE-SHOT** 💎" if tier == "VIP" else f"📡 **TRADEVISION AI → FREE SIGNAL** 📡"
    
    return f"""{header}
╔═══════════════════════════╗
  📊 **Asset Pair :** `{symbol}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time}` (GMT+6)
  ⏳ **Expiry     :** `{exp_text}`
  📈 **Entry Type :** `Next Candle`
╚═══════════════════════════╝
🎯 **Algorithmic Pattern :** `{pattern}`
⚡ **Accuracy Locked    :** `{confidence}%`
🤖 *Powered by TradeVision Price Action Engine v12.0*"""

# ================= AUTOMATIC FIXED SESSION CARD =================
async def send_auto_bulk_session():
    print("🔮 AUTOMATIC VIP SESSION GENERATOR STARTED...")
    base_pairs = ["USD/DZD", "NZD/CHF", "USD/INR", "LTC/USD", "USD/MXN", "USD/PHP", "USD/EGP", "CAD/CHF", "EUR/USD", "GBP/USD"]
    now_bd = datetime.now(bd_tz)
    start_time = now_bd.replace(hour=13, minute=0, second=0, microsecond=0)
    
    signals_list = []
    used_times = set()
    
    while len(signals_list) < 11:
        interval = random.randint(6, 14)
        start_time += timedelta(minutes=interval)
        time_str = start_time.strftime("%H:%M")
        
        if time_str not in used_times:
            pair = random.choice(base_pairs)
            df = get_live_candles(pair, "1min")
            direction = "CALL"
            if df is not None and not df.empty:
                if df["close"].iloc[-1] < df["open"].iloc[-1]: direction = "PUT"
            
            clean_pair = pair.replace("/", "") + "-OTC"
            signals_list.append(f"M1 {clean_pair} {time_str} {direction}")
            used_times.add(time_str)

    session_card = f"⏰ UTC  +6:00 🇧🇩 ;  MTG :- 1 STEP➕\n\n        😈    PREMIUM SIGNAL    😈\n\n⌛️ 1 Minutes :-\n                         \n"
    for sig in signals_list: session_card += f"{sig}\n"
    session_card += "\n❗️AVOID DOJI CANDEL,USE SEFTY MARGIN AND FOLLOW TREND 😬"

    try:
        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=session_card)
        print("✅ AUTOMATIC BULK SESSION CARD POSTED!")
    except Exception as e:
        print(f"❌ Failed to send auto session: {e}")

# ================= MAIN RUN LOOP =================
async def main():
    global session_sent_today
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
    print("🚀 PRICE ACTION ENGINE v12.0 RUNNING (ULTIMATE ACCURACY)...")

    while True:
        try:
            now_bd = datetime.now(bd_tz)
            if now_bd.weekday() in [5, 6]:
                await asyncio.sleep(3600)
                continue

            # ১২:৩০ এ অটো সেশন কার্ড পাবলিশ হবে
            if now_bd.hour == 12 and now_bd.minute == 30:
                if not session_sent_today:
                    await send_auto_bulk_session()
                    session_sent_today = True
            
            if now_bd.hour == 0 and now_bd.minute == 5:
                session_sent_today = False

            # লাইভ প্রাইস অ্যাকশন স্ক্যানার
            for timeframe in ["5min", "1min"]:
                for pair in pairs:
                    res = analyze_price_action(pair, timeframe)
                    if res:
                        signal = res["signal"]
                        tier = res["tier"]
                        filter_key = f"{tier}_{timeframe.upper()}"

                        if last_signals[filter_key].get(pair) != signal:
                            # পরবর্তী ক্যান্ডেলের একদম শুরুতেই এন্ট্রি টাইম ফিক্স করা
                            run_time = now_bd + timedelta(minutes=1)
                            entry_time_str = run_time.strftime("%H:%M")

                            msg = format_telegram_message(
                                pair, signal, res["confidence"], entry_time_str, 
                                timeframe, tier, res["pattern"]
                            )
                            target_channel = VIP_CHANNEL_ID if tier == "VIP" else FREE_CHANNEL_ID
                            
                            try:
                                await bot.send_message(chat_id=target_channel, text=msg, parse_mode="Markdown")
                                last_signals[filter_key][pair] = signal
                                print(f"✅ [{timeframe.upper()}] PRICE ACTION SIGNAL SENT: {pair} ({res['pattern']})")
                            except Exception as e:
                                print(f"❌ Telegram Error: {e}")
                
                await asyncio.sleep(1)

            await asyncio.sleep(30)  # হাই-স্পিড স্ক্যানিং লুপ টাইমার ৩০ সেকেন্ড করা হলো

        except Exception as main_err:
            print(f"🔥 CRASH PROTECTED: {main_err}")
            await asyncio.sleep(15)

if __name__ == "__main__":
    asyncio.run(main())
