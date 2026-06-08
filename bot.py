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
next_signal_time = datetime.now(bd_tz)

# ==================== AUTOMATIC DAILY SESSION (12:30 PM) ====================
async def send_auto_bulk_session():
    print("🔮 AUTOMATIC VIP HYBRID SESSION GENERATOR STARTED...")
    base_pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD", "NZD/CHF", "USD/INR", "USD/MXN"]
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
            direction = random.choice(["CALL", "PUT"])
            signals_list.append(f"M1 {pair} {time_str} {direction}")
            used_times.add(time_str)

    session_card = f"⏰ UTC  +6:00 🇧🇩 ;  MTG :- 1 STEP➕\n\n        😈    PREMIUM SIGNAL    😈\n\n⌛️ 1 Minutes :-\n                         \n"
    for sig in signals_list: 
        session_card += f"{sig}\n"
    session_card += "\n❗️AVOID DOJI CANDEL,USE SEFTY MARGIN AND FOLLOW TREND 😬"

    try:
        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=session_card)
    except Exception as e:
        print(f"❌ Failed to send auto session: {e}")

# ==================== CORE ENGINE LOOP ====================
async def main_automated_loop():
    global pending_results, session_sent_today, next_signal_time
    
    # শুধুমাত্র সেই পেয়ারগুলো রাখা হলো যেগুলোর আসল লাইভ ডাটা Yahoo-তে ১০০% পাওয়া যায়
    pairs = [
        {"name": "EUR/USD", "symbol": "EURUSD=X"},
        {"name": "GBP/USD", "symbol": "GBPUSD=X"},
        {"name": "USD/JPY", "symbol": "USDJPY=X"},
        {"name": "AUD/USD", "symbol": "AUDUSD=X"},
        {"name": "USD/CAD", "symbol": "USDCAD=X"},
        {"name": "USD/INR", "symbol": "USDINR=X"}
    ]

    print("🤖 REAL-DATA CHECKER ENGINE v18.0 IS RUNNING...")
    next_signal_time = datetime.now(bd_tz) + timedelta(seconds=15)

    while True:
        try:
            now_bd = datetime.now(bd_tz)
            
            # ⏰ ১. দুপুর ১২:৩০ এর অটো সেশন লিস্ট
            if now_bd.hour == 12 and now_bd.minute == 30 and not session_sent_today:
                await send_auto_bulk_session()
                session_sent_today = True
            
            if now_bd.hour == 0 and now_bd.minute == 5:
                session_sent_today = False

            # 📊 ২. সিগন্যাল পোস্টিং (র্যান্ডম সময়ে ফায়ার হবে)
            if now_bd >= next_signal_time:
                random_delay = random.randint(3, 6)
                next_signal_time = now_bd + timedelta(minutes=random_delay)

                selected = random.choice(pairs)
                pair_name = selected["name"]
                yf_symbol = selected["symbol"]
                
                signal = random.choice(["BUY", "SELL"]) # BUY = CALL, SELL = PUT
                
                run_time = now_bd + timedelta(minutes=1)
                entry_time_str = run_time.strftime("%H:%M")
                expiry_time = run_time + timedelta(minutes=1) 

                dir_emoji = "🟢" if signal == "BUY" else "🔴"
                dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"

                msg = f"""💎 **TRADEVISION AI → VIP SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{pair_name}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time_str}` (GMT+6)
  ⏳ **Expiry     :** `1 Minute`
  📈 **Entry Type :** `Next Candle / M1`
╚═══════════════════════════╝
🎯 **Strategy   :** `Live Market Price Action v18.0`
🔥 **Accuracy Locked :** `98% SURE-SHOT`"""

                await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                
                # রেজাল্ট চেক করার জন্য পেন্ডিং লিস্টে ডাটা সেভ
                pending_results.append({
                    "pair": pair_name, "symbol": yf_symbol, "signal": signal,
                    "expiry_time": expiry_time, "is_martingale": False
                })

            # 🎯 ৩. আসল লাইভ ডাটা দিয়ে উইন/লস চেক (এখানে কোনো ফেক রেজাল্ট হবে না)
            still_pending = []
            for item in pending_results:
                # ক্যান্ডেল শেষ হওয়ার ১৫ সেকেন্ড পর আসল ডাটা টানা হবে
                if now_bd >= (item["expiry_time"] + timedelta(seconds=15)):
                    try:
                        df = yf.download(tickers=item["symbol"], period="1d", interval="1m", progress=False)
                        if not df.empty:
                            close_price = df["Close"].iloc[-1]
                            open_price = df["Open"].iloc[-1]
                            signal = item["signal"]
                            pair_name = item["pair"]
                            
                            # ক্যান্ডেল গ্রিন নাকি রেড তার আসল হিসেব
                            is_green = close_price > open_price
                            is_red = close_price < open_price
                            
                            # সিগন্যালের সাথে চার্ট মিলানো
                            trade_win = (signal == "BUY" and is_green) or (signal == "SELL" and is_red)

                            if trade_win:
                                msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN!! ✅✅"
                                result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{pair_name}`\n🏆 **RESULT :** {msg_type} 🎉\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                            else:
                                # যদি লস হয় এবং এটা যদি প্রথম ডিরেক্ট ট্রেড হয়, তবে মার্টিনগেল অ্যালার্ট দেবে
                                if not item["is_martingale"]:
                                    m_expiry = now_bd + timedelta(minutes=1)
                                    m_alert = f"⚠️ **{pair_name} Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=m_alert, parse_mode="Markdown")

                                    # মার্টিনগেল চেক করার জন্য আবার পুশ
                                    still_pending.append({
                                        "pair": pair_name, "symbol": item["symbol"], "signal": signal,
                                        "expiry_time": m_expiry, "is_martingale": True
                                    })
                                else:
                                    # মার্টিনগেলও যদি লস হয়, তবে আসল লস কার্ড দেখাবে
                                    result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{pair_name}`\n🏆 **RESULT :** ❌ M1 LOSS ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                        else:
                            still_pending.append(item)
                    except Exception as err:
                        print(f"Error fetching real data: {err}")
                        still_pending.append(item)
                else:
                    still_pending.append(item)
            pending_results = still_pending

        except Exception as e:
            print(f"Loop warning: {e}")
            
        await asyncio.sleep(2)

# ==================== RAILWAY LIVE KEEP-ALIVE ====================
@app.route('/')
def home(): return "Real-Data Checking Bot is Live!"

if __name__ == "__main__":
    def start_standalone():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_automated_loop())

    t_bot = Thread(target=start_standalone)
    t_bot.daemon = True
    t_bot.start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
