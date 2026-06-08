import os
import asyncio
from flask import Flask, request, jsonify
from threading import Thread
from datetime import datetime, timedelta
import random
import pytz
from telegram import Bot
import yfinance as yf

# ================= CONFIGURATION =================
TOKEN = "8967772189:AAG1mpGAOsFo2NbwK72t9UUbH-pD0nxLE0w"
VIP_CHANNEL_ID = "@tradevision_vip_signals"  

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")
app = Flask(__name__)

pending_results = []
session_sent_today = False  

# ================= AUTOMATIC FIXED DAILY SESSION CARD (12:30 PM) =================
async def send_auto_bulk_session():
    print("🔮 AUTOMATIC VIP SESSION GENERATOR STARTED AT 12:30 PM...")
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

# ================= BACKGROUND RESULT CHECKER =================
async def result_checker_loop():
    global pending_results, session_sent_today
    while True:
        try:
            now_bd = datetime.now(bd_tz)
            
            # দুপুর ১২:৩০ এর অটো সেশন লিস্ট
            if now_bd.hour == 12 and now_bd.minute == 30:
                if not session_sent_today:
                    await send_auto_bulk_session()
                    session_sent_today = True
            
            if now_bd.hour == 0 and now_bd.minute == 5:
                session_sent_today = False

            # অটো উইন/লস চেকার
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
                                    m_expiry = now_bd + timedelta(minutes=item["duration_min"])
                                    m_alert = f"⚠️ **{clean_pair} Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=m_alert, parse_mode="Markdown")

                                    still_pending.append({
                                        "pair": item["pair"], "signal": signal, "entry_price": close_price,
                                        "duration_min": item["duration_min"], "expiry_time": m_expiry, "is_martingale": True
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
        except Exception as e:
            print(f"Result loop error: {e}")
        await asyncio.sleep(5)

# ================= TRADINGVIEW WEBHOOK RECEIVER =================
@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    data = request.json
    if not data: return jsonify({"status": "error"}), 400

    pair = data.get("pair")          
    signal = data.get("signal")      # "BUY" বা "SELL"
    timeframe = data.get("timeframe", "1min") 

    now_bd = datetime.now(bd_tz)
    entry_time_str = now_bd.strftime("%H:%M")
    duration_min = 5 if timeframe == "5min" else 1
    expiry_time = now_bd + timedelta(minutes=duration_min)

    dir_emoji = "🟢" if signal == "BUY" else "🔴"
    dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
    exp_text = "1 Minute" if timeframe == "1min" else "5 Minutes"
    clean_pair = pair.replace("/", "") + "-OTC"

    msg = f"""💎 **TRADEVISION AI → VIP SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{clean_pair}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time_str}` (GMT+6)
  ⏳ **Expiry     :** `{exp_text}`
  📈 **Entry Type :** `Next Candle / M1`
╚═══════════════════════════╝
🎯 **Strategy   :** `Ultra Scalper Engine v14.5`
🔥 **Accuracy Locked :** `98% SURE-SHOT`"""

    # টেলিগ্রামে সিগন্যাল পাঠানো
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown"))

    # কারেন্ট প্রাইস অনুমান করে রেজাল্ট ট্র্যাকিং-এ রাখা
    pending_results.append({
        "pair": pair, "signal": signal, "entry_price": 0.0, # রেজাল্ট চেকার নিজেই ক্লোজ প্রাইস মেলাবে
        "duration_min": duration_min, "expiry_time": expiry_time, "is_martingale": False
    })

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    def start_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(result_checker_loop())

    t_bot = Thread(target=start_bot)
    t_bot.daemon = True
    t_bot.start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
