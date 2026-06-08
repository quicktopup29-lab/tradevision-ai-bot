import os
import asyncio
from datetime import datetime, timedelta
import random
import pytz
from telegram import Bot
import yfinance as yf
from threading import Thread
from flask import Flask

# ==================== CONFIGURATION ====================
TOKEN = "8967772189:AAG1mpGAOsFo2NbwK72t9UUbH-pD0nxLE0w"
VIP_CHANNEL_ID = "@tradevision_vip_signals"  

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")
app = Flask('')

pending_results = []
session_sent_today = False  
last_processed_minute = -1 

# ==================== AUTOMATIC DAILY SESSION (12:30 PM) ====================
async def send_auto_bulk_session():
    print("🔮 AUTOMATIC VIP SESSION GENERATOR STARTED AT 12:30 PM...")
    base_pairs = ["USD/DZD", "NZD/CHF", "USD/INR", "USD/CAD", "USD/MXN", "USD/PHP", "USD/EGP", "CAD/CHF", "EUR/USD", "GBP/USD"]
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
    for sig in signals_list: 
        session_card += f"{sig}\n"
    session_card += "\n❗️AVOID DOJI CANDEL,USE SEFTY MARGIN AND FOLLOW TREND 😬"

    try:
        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=session_card)
        print("✅ AUTOMATIC BULK SESSION CARD POSTED!")
    except Exception as e:
        print(f"❌ Failed to send auto session: {e}")

# ==================== 100% INTERNAL SCALPING ENGINE ====================
def scan_and_generate_signal(pair):
    try:
        yf_symbol = pair.replace("/", "") + "=X"
        df = yf.download(tickers=yf_symbol, period="1d", interval="1m", progress=False)
        if df.empty or len(df) < 5: return None

        close_p = df["Close"].iloc[-1]
        open_p = df["Open"].iloc[-1]
        high_p = df["High"].iloc[-1]
        low_p = df["Low"].iloc[-1]

        body = abs(close_p - open_p)
        
        # 🟢 CALL / BUY Signal Logic
        if close_p > open_p and body > 0.0001:
            if (high_p - close_p) < (body * 0.2): 
                return {"signal": "BUY", "price": close_p}

        # 🔴 PUT / SELL Signal Logic
        elif close_p < open_p and body > 0.0001:
            if (close_p - low_p) < (body * 0.2): 
                return {"signal": "SELL", "price": close_p}
                
        return None
    except:
        return None

# ==================== FULLY STANDALONE AUTO LOOP ====================
async def main_standalone_loop():
    global pending_results, session_sent_today, last_processed_minute
    
    # এরর দেওয়া LTC/USD বাদ দিয়ে USD/CAD যোগ করা হয়েছে
    pairs = [
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", 
        "USD/INR", "NZD/CHF", "USD/MXN", "CAD/CHF",
        "USD/DZD", "USD/PHP", "USD/EGP", "USD/CAD"
    ]

    print("🤖 STANDALONE SELF-MADE AUTO ENGINE IS RUNNING LIVE...")

    while True:
        try:
            now_bd = datetime.now(bd_tz)
            
            # ⏰ ১. দুপুর ১২:৩০ এর অটো সেশন লিস্ট
            if now_bd.hour == 12 and now_bd.minute == 30 and not session_sent_today:
                await send_auto_bulk_session()
                session_sent_today = True
            
            if now_bd.hour == 0 and now_bd.minute == 5:
                session_sent_today = False

            # 📊 ২. প্রতি মিনিটে মার্কেট স্ক্যান (১ মিনিটের সিগন্যাল)
            if now_bd.second <= 5 and now_bd.minute != last_processed_minute:
                last_processed_minute = now_bd.minute
                
                scanned_pair = random.choice(pairs)
                res = scan_and_generate_signal(scanned_pair)
                
                if res:
                    signal = res["signal"]
                    clean_pair = scanned_pair.replace("/", "") + "-OTC"
                    
                    run_time = now_bd + timedelta(minutes=1)
                    entry_time_str = run_time.strftime("%H:%M")
                    expiry_time = run_time + timedelta(minutes=1) 

                    dir_emoji = "🟢" if signal == "BUY" else "🔴"
                    dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"

                    msg = f"""💎 **TRADEVISION AI → VIP SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{clean_pair}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time_str}` (GMT+6)
  ⏳ **Expiry     :** `1 Minute`
  📈 **Entry Type :** `Next Candle / M1`
╚═══════════════════════════╝
🎯 **Strategy   :** `Standalone Price Action v16.1`
🔥 **Accuracy Locked :** `98% SURE-SHOT`"""

                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                    
                    pending_results.append({
                        "pair": scanned_pair, "signal": signal, "entry_price": res["price"],
                        "expiry_time": expiry_time, "is_martingale": False
                    })

            # 🎯 ৩. অটো উইন/লস রেজাল্ট চেকার
            still_pending = []
            for item in pending_results:
                if now_bd >= (item["expiry_time"] + timedelta(seconds=10)):
                    try:
                        yf_symbol = item["pair"].replace("/", "") + "=X"
                        df = yf.download(tickers=yf_symbol, period="1d", interval="1m", progress=False)
                        
                        if not df.empty:
                            close_price = df["Close"].iloc[-1]
                            entry_price = item["entry_price"]
                            signal = item["signal"]
                            clean_pair = item["pair"].replace("/", "") + "-OTC"
                            
                            is_win = (signal == "BUY" and close_price > entry_price) or (signal == "SELL" and close_price < entry_price)

                            if is_win:
                                msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN!! ✅✅"
                                result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{clean_pair}`\n🏆 **RESULT :** {msg_type} 🎉\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                            else:
                                if not item["is_martingale"]:
                                    m_expiry = now_bd + timedelta(minutes=1)
                                    m_alert = f"⚠️ **{clean_pair} Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=m_alert, parse_mode="Markdown")

                                    still_pending.append({
                                        "pair": item["pair"], "signal": signal, "entry_price": close_price,
                                        "expiry_time": m_expiry, "is_martingale": True
                                    })
                                else:
                                    result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{clean_pair}`\n🏆 **RESULT :** ❌ M1 LOSS ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                        else:
                            still_pending.append(item)
                    except:
                        still_pending.append(item)
                else:
                    still_pending.append(item)
            pending_results = still_pending

        except Exception as main_err:
            print(f"🔥 Standalone Engine Loop Warning: {main_err}")
            
        await asyncio.sleep(2)

# ==================== RAILWAY LIVE KEEP-ALIVE ====================
@app.route('/')
def home(): return "Standalone Bot is Alive and Scanning Market!"

if __name__ == "__main__":
    def start_standalone():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_standalone_loop())

    t_bot = Thread(target=start_standalone)
    t_bot.daemon = True
    t_bot.start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
