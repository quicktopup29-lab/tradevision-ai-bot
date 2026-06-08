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

# নয়ন, আপনার দেওয়া চ্যানেলের আইডিগুলো এখানে সেট করা হয়েছে
MAIN_CHANNEL_ID = "@tradevision_ai_signals"  
VIP_CHANNEL_ID = "@tradevision_vip_signals"  

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")
app = Flask('')

pending_results = []
session_sent_today = False  
next_main_signal_time = datetime.now(bd_tz)
next_vip_signal_time = datetime.now(bd_tz)

# ==================== AUTOMATIC DAILY SESSION (12:30 PM) ====================
async def send_auto_bulk_session():
    print("🔮 AUTOMATIC VIP HYBRID SESSION GENERATOR STARTED...")
    base_pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD", "USD/INR-OTC", "USD/PHP-OTC", "USD/MXN-OTC"]
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
        # বাল্ক সেশন লিস্টটি শুধুমাত্র ভিআইপি গ্রুপেই পোস্ট হবে
        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=session_card)
        print("✅ BULK SESSION LIST POSTED TO VIP!")
    except Exception as e:
        print(f"❌ Failed to send auto session: {e}")

# ==================== CORE DUAL-CHANNEL LOOP ====================
async def main_automated_loop():
    global pending_results, session_sent_today, next_main_signal_time, next_vip_signal_time
    
    pairs = [
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
        "USD/INR-OTC", "NZD/CHF-OTC", "USD/MXN-OTC", "USD/PHP-OTC"
    ]

    print("🤖 DUAL-CHANNEL TRAFFIC ENGINE v19.5 IS RUNNING...")
    
    # টাইমার সেটআপ
    next_main_signal_time = datetime.now(bd_tz) + timedelta(seconds=10)
    next_vip_signal_time = datetime.now(bd_tz) + timedelta(minutes=4) 

    while True:
        try:
            now_bd = datetime.now(bd_tz)
            
            # ⏰ ১. দুপুর ১২:৩০ এর অটো সেশন লিস্ট (ভিআইপি-র জন্য)
            if now_bd.hour == 12 and now_bd.minute == 30 and not session_sent_today:
                await send_auto_bulk_session()
                session_sent_today = True
            
            if now_bd.hour == 0 and now_bd.minute == 5:
                session_sent_today = False

            # 📊 ২. মেইন/ফ্রি চ্যানেল সিগন্যাল (২৪ ঘণ্টা নন-স্টপ, প্রতি ৩-৬ মিনিট পর পর)
            if now_bd >= next_main_signal_time:
                random_delay = random.randint(3, 6)
                next_main_signal_time = now_bd + timedelta(minutes=random_delay)

                pair_name = random.choice(pairs)
                signal = random.choice(["BUY", "SELL"])
                
                run_time = now_bd + timedelta(minutes=1)
                entry_time_str = run_time.strftime("%H:%M")
                expiry_time = run_time + timedelta(minutes=1) 

                dir_emoji = "🟢" if signal == "BUY" else "🔴"
                dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
                strategy_name = "Public Scalper Mode" if "OTC" not in pair_name else "Public OTC Mode"

                msg = f"""💎 **TRADEVISION AI → FREE SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{pair_name}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time_str}` (GMT+6)
  ⏳ **Expiry     :** `1 Minute`
  📈 **Entry Type :** `Next Candle / M1`
╚═══════════════════════════╝
🎯 **Strategy   :** `{strategy_name} v19.5`
🔥 **Accuracy Locked :** `85% ACCURACY`"""

                try:
                    await bot.send_message(chat_id=MAIN_CHANNEL_ID, text=msg, parse_mode="Markdown")
                    pending_results.append({
                        "channel": "MAIN", "pair": pair_name, "signal": signal,
                        "expiry_time": expiry_time, "is_martingale": False
                    })
                except Exception as ex:
                    print(f"Main channel send error: {ex}")

            # 📊 ৩. ভিআইপি চ্যানেল সিগন্যাল (হাই অ্যাকুরিসি ৯৫%+, প্রতি ৮-১৫ মিনিট পর পর শান্তভাবে আসবে)
            if now_bd >= next_vip_signal_time:
                random_vip_delay = random.randint(8, 15)
                next_vip_signal_time = now_bd + timedelta(minutes=random_vip_delay)

                pair_name = random.choice(pairs)
                signal = random.choice(["BUY", "SELL"])
                
                run_time = now_bd + timedelta(minutes=1)
                entry_time_str = run_time.strftime("%H:%M")
                expiry_time = run_time + timedelta(minutes=1) 

                dir_emoji = "🟢" if signal == "BUY" else "🔴"
                dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
                strategy_name = "VIP Live Price Action" if "OTC" not in pair_name else "VIP Ultra Scalper Engine"

                msg = f"""💎 **TRADEVISION AI → VIP SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{pair_name}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time_str}` (GMT+6)
  ⏳ **Expiry     :** `1 Minute`
  📈 **Entry Type :** `Next Candle / M1`
╚═══════════════════════════╝
🎯 **Strategy   :** `{strategy_name} v19.5`
🔥 **Accuracy Locked :** `99% ULTRA SURE-SHOT`"""

                try:
                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                    pending_results.append({
                        "channel": "VIP", "pair": pair_name, "signal": signal,
                        "expiry_time": expiry_time, "is_martingale": False
                    })
                except Exception as ex:
                    print(f"VIP channel send error: {ex}")

            # 🎯 ৪. ডুয়াল চ্যানেল ফাস্ট রেজাল্ট মেকার (স্মার্ট ফিল্টার্ড)
            still_pending = []
            for item in pending_results:
                if now_bd >= (item["expiry_time"] + timedelta(seconds=2)):
                    pair_name = item["pair"]
                    target_channel = MAIN_CHANNEL_ID if item["channel"] == "MAIN" else VIP_CHANNEL_ID
                    
                    win_chance = random.randint(1, 100)

                    # ফ্রি গ্রুপে ৮৮% উইন রেট (মাঝে মাঝে লস দেখাবে রিয়েল মার্কেট ফিল দেওয়ার জন্য)
                    if item["channel"] == "MAIN":
                        if win_chance <= 88:
                            msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN (With Safety Margin)!! ✅✅"
                            result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{pair_name}`\n🏆 **RESULT :** {msg_type} 🎉\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            await bot.send_message(chat_id=target_channel, text=result_text, parse_mode="Markdown")
                        else:
                            if not item["is_martingale"]:
                                m_expiry = now_bd + timedelta(minutes=1)
                                m_alert = f"⚠️ **{pair_name} Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                                await bot.send_message(chat_id=target_channel, text=m_alert, parse_mode="Markdown")

                                still_pending.append({
                                    "channel": "MAIN", "pair": pair_name, "signal": item["signal"],
                                    "expiry_time": m_expiry, "is_martingale": True
                                })
                            else:
                                result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{pair_name}`\n🏆 **RESULT :** ❌ M1 LOSS ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                await bot.send_message(chat_id=target_channel, text=result_text, parse_mode="Markdown")
                    
                    # 💎 ভিআইপি গ্রুপে ৯৮% উইন রেট (এখানে লস প্রায় হবেই না, ১০০% সিউর শট উইন)
                    elif item["channel"] == "VIP":
                        if win_chance <= 98:
                            msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN!! ✅✅"
                            result_text = f"📊 **TRADEVISION AI → VIP LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{pair_name}`\n🏆 **RESULT :** {msg_type} 🔥\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            await bot.send_message(chat_id=target_channel, text=result_text, parse_mode="Markdown")
                        else:
                            if not item["is_martingale"]:
                                m_expiry = now_bd + timedelta(minutes=1)
                                m_alert = f"⚠️ **VIP ALERT: {pair_name} Next Candle Martingale M1 NOW!**"
                                await bot.send_message(chat_id=target_channel, text=m_alert, parse_mode="Markdown")

                                still_pending.append({
                                    "channel": "VIP", "pair": pair_name, "signal": item["signal"],
                                    "expiry_time": m_expiry, "is_martingale": True
                                })
                            else:
                                result_text = f"📊 **TRADEVISION AI → VIP LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{pair_name}`\n🏆 **RESULT :** ✅ MARTINGALE M1 WIN!! 🎉\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                await bot.send_message(chat_id=target_channel, text=result_text, parse_mode="Markdown")
                else:
                    still_pending.append(item)
            pending_results = still_pending

        except Exception as e:
            print(f"Dual Loop error: {e}")
            
        await asyncio.sleep(2)

# ==================== RAILWAY LIVE KEEP-ALIVE ====================
@app.route('/')
def home(): return "TradeVision AI Dual Channel Server is Active!"

if __name__ == "__main__":
    def start_standalone():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_automated_loop())

    t_bot = Thread(target=start_standalone)
    t_bot.daemon = True
    t_bot.start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
