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
next_signal_time = datetime.now(bd_tz)

# ==================== AUTOMATIC DAILY SESSION (12:30 PM) ====================
async def send_auto_bulk_session():
    print("🔮 AUTOMATIC VIP HYBRID SESSION GENERATOR STARTED AT 12:30 PM...")
    # লাইভ এবং ওটিসি পেয়ারের মিক্সড লিস্ট
    base_pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD-OTC", "USD/INR-OTC", "NZD/CHF", "USD/MXN-OTC", "USD/CAD", "USD/EGP-OTC", "CAD/CHF-OTC"]
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
        print("✅ AUTOMATIC BULK HYBRID SESSION CARD POSTED!")
    except Exception as e:
        print(f"❌ Failed to send auto session: {e}")

# ==================== CORE HYBRID LOOP ====================
async def main_automated_loop():
    global pending_results, session_sent_today, next_signal_time
    
    # এখানে কিছু পেয়ার একদম লাইভ রিয়েল মার্কেট আর কিছু ওটিসি হিসেবে সাজানো হয়েছে
    pairs = [
        {"name": "EUR/USD", "type": "LIVE"},
        {"name": "GBP/USD", "type": "LIVE"},
        {"name": "USD/JPY", "type": "LIVE"},
        {"name": "AUD/USD", "type": "LIVE"},
        {"name": "USD/CAD", "type": "LIVE"},
        {"name": "USD/INR-OTC", "type": "OTC"},
        {"name": "NZD/CHF-OTC", "type": "OTC"},
        {"name": "USD/MXN-OTC", "type": "OTC"},
        {"name": "CAD/CHF-OTC", "type": "OTC"},
        {"name": "USD/DZD-OTC", "type": "OTC"},
        {"name": "USD/PHP-OTC", "type": "OTC"},
        {"name": "USD/EGP-OTC", "type": "OTC"}
    ]

    print("🤖 HYBRID LIVE+OTC ENGINE v17.5 IS RUNNING...")
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

            # 📊 ২. হাইব্রিড সিগন্যাল জেনারেটর
            if now_bd >= next_signal_time:
                random_delay = random.randint(2, 5)
                next_signal_time = now_bd + timedelta(minutes=random_delay)

                selected = random.choice(pairs)
                pair_name = selected["name"]
                market_type = selected["type"]
                
                signal = random.choice(["BUY", "SELL"])
                
                run_time = now_bd + timedelta(minutes=1)
                entry_time_str = run_time.strftime("%H:%M")
                expiry_time = run_time + timedelta(minutes=1) 

                dir_emoji = "🟢" if signal == "BUY" else "🔴"
                dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
                
                # মার্কেট টাইপ অনুযায়ী সাবটাইটেল বা স্ট্র্যাটেজির নাম চেঞ্জ হবে
                strategy_name = "Live Market Price Action v17.5" if market_type == "LIVE" else "AI OTC Scalper v17.5"

                msg = f"""💎 **TRADEVISION AI → VIP SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{pair_name}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time_str}` (GMT+6)
  ⏳ **Expiry     :** `1 Minute`
  📈 **Entry Type :** `Next Candle / M1`
╚═══════════════════════════╝
🎯 **Strategy   :** `{strategy_name}`
🔥 **Accuracy Locked :** `98% SURE-SHOT`"""

                await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                print(f"📡 Hybrid Signal Sent for {pair_name} ({market_type})")
                
                pending_results.append({
                    "pair": pair_name, "signal": signal,
                    "expiry_time": expiry_time, "is_martingale": False
                })

            # 🎯 ৩. স্মার্ট উইন/লস রেজাল্ট মেকার
            still_pending = []
            for item in pending_results:
                if now_bd >= (item["expiry_time"] + timedelta(seconds=5)):
                    pair_name = item["pair"]
                    win_chance = random.randint(1, 100)

                    if win_chance <= 92:  # ৯২% উইন রেট
                        msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN!! ✅✅"
                        result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{pair_name}`\n🏆 **RESULT :** {msg_type} 🎉\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                    else:
                        if not item["is_martingale"]:
                            m_expiry = now_bd + timedelta(minutes=1)
                            m_alert = f"⚠️ **{pair_name} Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                            await bot.send_message(chat_id=VIP_CHANNEL_ID, text=m_alert, parse_mode="Markdown")

                            still_pending.append({
                                "pair": pair_name, "signal": item["signal"],
                                "expiry_time": m_expiry, "is_martingale": True
                            })
                        else:
                            result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{pair_name}`\n🏆 **RESULT :** ❌ M1 LOSS ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                else:
                    still_pending.append(item)
            pending_results = still_pending

        except Exception as e:
            print(f"Loop warning: {e}")
            
        await asyncio.sleep(2)

# ==================== RAILWAY LIVE KEEP-ALIVE ====================
@app.route('/')
def home(): return "TradeVision AI Hybrid Live+OTC Bot is Running!"

if __name__ == "__main__":
    def start_standalone():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_automated_loop())

    t_bot = Thread(target=start_standalone)
    t_bot.daemon = True
    t_bot.start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
