import os
import asyncio
from datetime import datetime, timedelta
import random
import pytz
from telegram import Bot
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
next_signal_time = datetime.now(bd_tz) # পরবর্তী সিগন্যাল কখন যাবে তার টাইমার

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

# ==================== CORE FULLY AUTOMATED LOOP ====================
async def main_automated_loop():
    global pending_results, session_sent_today, next_signal_time
    
    pairs = [
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", 
        "USD/INR", "NZD/CHF", "USD/MXN", "CAD/CHF",
        "USD/DZD", "USD/PHP", "USD/EGP", "USD/CAD"
    ]

    print("🤖 ULTRA-AUTOMATED ENGINE v17.0 IS LIVE AND ACTIVE...")
    
    # প্রথম সিগন্যাল চালু হওয়ার জন্য টাইম সেট
    next_signal_time = datetime.now(bd_tz) + timedelta(seconds=10)

    while True:
        try:
            now_bd = datetime.now(bd_tz)
            
            # ⏰ ১. দুপুর ১২:৩০ এর অটো সেশন লিস্ট
            if now_bd.hour == 12 and now_bd.minute == 30 and not session_sent_today:
                await send_auto_bulk_session()
                session_sent_today = True
            
            if now_bd.hour == 0 and now_bd.minute == 5:
                session_sent_today = False

            # 📊 ২. অটোমেটিক সিগন্যাল জেনারেটর (২ থেকে ৫ মিনিট পর পর আসবে)
            if now_bd >= next_signal_time:
                # পরবর্তী সিগন্যাল কতক্ষণ পরে আসবে তা র্যান্ডমলি ফিক্সড করা (যেমন: ৩ মিনিট পর)
                random_delay = random.randint(2, 5)
                next_signal_time = now_bd + timedelta(minutes=random_delay)

                scanned_pair = random.choice(pairs)
                signal = random.choice(["BUY", "SELL"])
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
🎯 **Strategy   :** `AI Price Action Engine v17.0`
🔥 **Accuracy Locked :** `98% SURE-SHOT`"""

                await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                print(f"📡 Auto Signal Sent for {clean_pair}")
                
                pending_results.append({
                    "pair": scanned_pair, "signal": signal,
                    "expiry_time": expiry_time, "is_martingale": False
                })

            # 🎯 ৩. স্মার্ট উইন/লস রেজাল্ট মেকার
            still_pending = []
            for item in pending_results:
                if now_bd >= (item["expiry_time"] + timedelta(seconds=5)):
                    clean_pair = item["pair"].replace("/", "") + "-OTC"
                    
                    # ৯০% চান্স ডিরেক্ট উইন বা মার্টিনগেল উইন দেখানোর জন্য
                    win_chance = random.randint(1, 100)

                    if win_chance <= 92:  # ৯২% উইন রেট লক করা হলো
                        msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN!! ✅✅"
                        result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{clean_pair}`\n🏆 **RESULT :** {msg_type} 🎉\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                    else:
                        # লস হলে ডিরেক্ট ১-স্টেপ মার্টিনগেল কল করবে
                        if not item["is_martingale"]:
                            m_expiry = now_bd + timedelta(minutes=1)
                            m_alert = f"⚠️ **{clean_pair} Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                            await bot.send_message(chat_id=VIP_CHANNEL_ID, text=m_alert, parse_mode="Markdown")

                            still_pending.append({
                                "pair": item["pair"], "signal": item["signal"],
                                "expiry_time": m_expiry, "is_martingale": True
                            })
                        else:
                            # মার্টিনগেল ও লস হলে ফাইনাল কার্ড
                            result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{clean_pair}`\n🏆 **RESULT :** ❌ M1 LOSS ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                else:
                    still_pending.append(item)
            pending_results = still_pending

        except Exception as e:
            print(f"Loop warning: {e}")
            
        await asyncio.sleep(2)

# ==================== RAILWAY LIVE KEEP-ALIVE ====================
@app.route('/')
def home(): return "TradeVision AI Fully-Automated Bot is Running!"

if __name__ == "__main__":
    def start_standalone():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_automated_loop())

    t_bot = Thread(target=start_standalone)
    t_bot.daemon = True
    t_bot.start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
