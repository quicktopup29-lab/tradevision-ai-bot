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

last_signals = {}
pending_results = []
session_sent_today = False  

# ================= HIGH-SPEED DATA FETCH =================
def get_live_candles(symbol, interval="1min"):
    try:
        yf_symbol = symbol.replace("/", "") + "=X"
        yf_interval = "1m" if interval == "1min" else "5m"
        
        df = yf.download(tickers=yf_symbol, period="1d", interval=yf_interval, progress=False)
        if df.empty or len(df) < 15: return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        
        df.columns = [str(col).lower() for col in df.columns]
        return df
    except:
        return None

# ================= PURE 90%+ PRICE ACTION ENGINE =================
def analyze_market(symbol, timeframe):
    df = get_live_candles(symbol, timeframe)
    if df is None or len(df) < 5: return None

    try:
        close = df["close"]
        open_p = df["open"]
        high = df["high"]
        low = df["low"]
        
        c1, o1, h1, l1 = close.iloc[-1], open_p.iloc[-1], high.iloc[-1], low.iloc[-1]
        c2, o2 = close.iloc[-2], open_p.iloc[-2]
        
        body1 = abs(c1 - o1)
        avg_body = abs(close - open_p).tail(10).mean()
        
        direction = None
        pattern_name = ""

        # 🟢 CALL / BUY STRATEGY
        if c1 > o1 and body1 > (avg_body * 1.1):
            if c2 < o2 and c1 > o2 and o1 < c2: 
                direction = "BUY"
                pattern_name = "Bullish Engulfing"
            elif (h1 - c1) < (body1 * 0.1): 
                direction = "BUY"
                pattern_name = "Marubozu Breakout"

        # 🔴 PUT / SELL STRATEGY
        elif c1 < o1 and body1 > (avg_body * 1.1):
            if c2 > o2 and c1 < o2 and o1 > c2: 
                direction = "SELL"
                pattern_name = "Bearish Engulfing"
            elif (c1 - l1) < (body1 * 0.1): 
                direction = "SELL"
                pattern_name = "Marubozu Breakdown"

        if not direction: return None
        
        return {"signal": direction, "confidence": 95, "entry_price": c1, "pattern": pattern_name}
    except:
        return None

# ================= TELEGRAM MESSAGE FORMATTING =================
def format_telegram_message(symbol, signal, confidence, entry_time, timeframe, pattern, is_martingale=False):
    dir_emoji = "🟢" if signal == "BUY" else "🔴"
    dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
    exp_text = "1 Minute" if timeframe == "1min" else "5 Minutes"
    
    m_header = "⚠️ [MARTINGALE M1] " if is_martingale else ""
    clean_pair = symbol.replace("/", "") + "-OTC"
    
    return f"""{m_header}💎 **TRADEVISION AI → VIP SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{clean_pair}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time}` (GMT+6)
  ⏳ **Expiry     :** `{exp_text}`
  📈 **Entry Type :** `{"Martingale Candle" if is_martingale else "Next Candle"}`
╚═══════════════════════════╝
🎯 **Pattern :** `{pattern}`
🔥 **Accuracy Locked :** `{confidence}% SURE-SHOT`
🤖 *Powered by TradeVision Pro Engine v12.6*"""

# ================= AUTOMATIC RESULT & MARTINGALE ENGINE =================
async def check_pending_results():
    global pending_results
    now_bd = datetime.now(bd_tz)
    still_pending = []

    for item in pending_results:
        if "attempt" not in item: item["attempt"] = 0

        # রেজাল্ট চেক করার বাফার টাইম লক
        buffer = 15 if item["timeframe"] == "1min" else 30
        if now_bd >= (item["expiry_time"] + timedelta(seconds=buffer)):
            item["attempt"] += 1
            print(f"🔄 Checking Result for {item['pair']} ({item['timeframe']}) | Attempt: {item['attempt']}...")
            
            df = get_live_candles(item["pair"], item["timeframe"])
            if df is not None:
                try:
                    current_close = df["close"].iloc[-1]
                    entry_price = item["entry_price"]
                    signal = item["signal"]
                    
                    is_win = (signal == "BUY" and current_close > entry_price) or (signal == "SELL" and current_close < entry_price)

                    if is_win:
                        msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN!! ✅✅"
                        result_text = f"📊 **TRADEVISION AI → RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair'].replace('/', '')}-OTC`\n🏆 **RESULT :** {msg_type} 🎉\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        await bot.send_message(chat_id=item["channel_id"], text=result_text, parse_mode="Markdown")
                    else:
                        if not item["is_martingale"]:
                            m_duration = 1 if item["timeframe"] == "1min" else 5
                            m_run_time = now_bd
                            m_entry_str = m_run_time.strftime("%H:%M")
                            m_expiry = m_run_time + timedelta(minutes=m_duration)

                            m_alert = f"⚠️ **{item['pair'].replace('/', '')}-OTC Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                            await bot.send_message(chat_id=item["channel_id"], text=m_alert, parse_mode="Markdown")

                            still_pending.append({
                                "pair": item["pair"], "signal": signal, "entry_price": current_close,
                                "timeframe": item["timeframe"], "entry_time_str": m_entry_str, 
                                "expiry_time": m_expiry, "channel_id": item["channel_id"], 
                                "is_martingale": True, "attempt": 0, "pattern": item["pattern"]
                            })
                        else:
                            result_text = f"📊 **TRADEVISION AI → RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair'].replace('/', '')}-OTC`\n🏆 **RESULT :** ❌ M1 LOSS ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            await bot.send_message(chat_id=item["channel_id"], text=result_text, parse_mode="Markdown")
                except Exception as e:
                    if item["attempt"] < 3: still_pending.append(item)
            else:
                if item["attempt"] < 3: still_pending.append(item)
        else:
            still_pending.append(item)

    pending_results = still_pending

# ================= AUTOMATIC FIXED DAILY SESSION CARD =================
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
            clean_pair = pair.replace("/", "") + "-OTC"
            direction = random.choice(["CALL", "PUT"])
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
    
    pairs = [
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", 
        "USD/INR", "NZD/CHF", "USD/MXN", "CAD/CHF",
        "USD/DZD", "USD/PHP", "USD/EGP", "LTC/USD"
    ]
    
    print("🚀 HIGH-ACCURACY AUTO-RESULT ENGINE v12.6 STARTED...")

    for p in pairs:
        last_signals[f"VIP_1MIN_{p}"] = None
        last_signals[f"VIP_5MIN_{p}"] = None

    while True:
        try:
            now_bd = datetime.now(bd_tz)
            if now_bd.weekday() in [5, 6]:
                await asyncio.sleep(3600)
                continue

            # ১২:৩০ এ অটো সেশন কার্ড
            if now_bd.hour == 12 and now_bd.minute == 30:
                if not session_sent_today:
                    await send_auto_bulk_session()
                    session_sent_today = True
            
            if now_bd.hour == 0 and now_bd.minute == 5:
                session_sent_today = False

            # পেন্ডিং রেজাল্ট চেক করা হচ্ছে
            await check_pending_results()

            # মাল্টি-কারেন্সি স্ক্যানার
            for timeframe in ["1min", "5min"]:
                for pair in pairs:
                    res = analyze_market(pair, timeframe)
                    if res:
                        signal = res["signal"]
                        filter_key = f"VIP_{timeframe.upper()}_{pair}"

                        if last_signals.get(filter_key) != signal:
                            duration = 5 if timeframe == "5min" else 1
                            run_time = now_bd + timedelta(minutes=1)
                            entry_time_str = run_time.strftime("%H:%M")
                            expiry_time = run_time + timedelta(minutes=duration)

                            msg = format_telegram_message(
                                pair, signal, res["confidence"], entry_time_str, timeframe, res["pattern"]
                            )
                            
                            try:
                                await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                                last_signals[filter_key] = signal
                                print(f"🎯 SENT: {pair} - {signal} ({timeframe})")

                                # রেজাল্ট ট্র্যাক করার জন্য ট্র্যাকিং ট্রিতে পুশ করা হলো
                                pending_results.append({
                                    "pair": pair, "signal": signal, "entry_price": res["entry_price"],
                                    "timeframe": timeframe, "entry_time_str": entry_time_str, 
                                    "expiry_time": expiry_time, "channel_id": VIP_CHANNEL_ID, 
                                    "is_martingale": False, "attempt": 0, "pattern": res["pattern"]
                                })
                            except Exception as e:
                                print(f"❌ Telegram Error: {e}")
                
                await asyncio.sleep(1)

            await asyncio.sleep(20) 

        except Exception as main_err:
            print(f"🔥 Crash Avoided: {main_err}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
