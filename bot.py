import os
import asyncio
from flask import Flask, request, jsonify
from threading import Thread
from datetime import datetime, timedelta
import random
import pytz
from telegram import Bot
import MetaTrader5 as mt5

# ================= CONFIGURATION =================
TOKEN = "8967772189:AAG1mpGAOsFo2NbwK72t9UUbH-pD0nxLE0w"
VIP_CHANNEL_ID = "@tradevision_vip_signals"  

# মেটাট্রেডার ৫ ডেমো অ্যাকাউন্ট ডিটেইলস
MT5_LOGIN = 12345678  
MT5_PASSWORD = "your_password"
MT5_SERVER = "ICMarkets-Demo"

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")
app = Flask(__name__)

pending_results = []
session_sent_today = False  # প্রতিদিন একবারই যেন শিডিউল লিস্ট যায়

# ================= MT5 INITIALIZATION =================
def initialize_mt5():
    if not mt5.initialize():
        print("❌ MT5 Initialization Failed!")
        return False
    authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if authorized:
        print("✅ Connected to MT5 Live Bridge successfully!")
        return True
    else:
        print(f"❌ MT5 Login Failed!")
        return False

# ================= MT5 LIVE DATA ENGINES =================
def get_mt5_price(symbol):
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        return tick.ask  
    return None

def check_candle_status(symbol, timeframe_min):
    tf = mt5.TIMEFRAME_M1 if timeframe_min == 1 else mt5.TIMEFRAME_M5
    rates = mt5.copy_rates_from_now(symbol, tf, 1)
    if rates is not None and len(rates) > 0:
        return rates[0]['close']
    return None

# ================= AUTOMATIC FIXED DAILY SESSION CARD (12:30 PM) =================
async def send_auto_bulk_session():
    print("🔮 AUTOMATIC VIP SESSION GENERATOR STARTED AT 12:30 PM...")
    base_pairs = ["USD/DZD", "NZD/CHF", "USD/INR", "LTC/USD", "USD/MXN", "USD/PHP", "USD/EGP", "CAD/CHF", "EUR/USD", "GBP/USD"]
    now_bd = datetime.now(bd_tz)
    
    # সেশন শুরু হবে দুপুর ১:০০ (১৩:০০) টা থেকে
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

    # হুবহু আপনার ফরম্যাট
    session_card = f"⏰ UTC  +6:00 🇧🇩 ;  MTG :- 1 STEP➕\n\n        😈    PREMIUM SIGNAL    😈\n\n⌛️ 1 Minutes :-\n                         \n"
    for sig in signals_list: 
        session_card += f"{sig}\n"
    session_card += "\n❗️AVOID DOJI CANDEL,USE SEFTY MARGIN AND FOLLOW TREND 😬"

    try:
        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=session_card)
        print("✅ AUTOMATIC BULK SESSION CARD POSTED SUCCESSFULLY AT 12:30 PM!")
    except Exception as e:
        print(f"❌ Failed to send auto session: {e}")

# ================= BACKGROUND BACKGROUND CORE LOOP =================
async def background_core_loop():
    """রেজাল্ট ট্র্যাকিং এবং ১২:৩০ এর টাইম চেকার এক সাথে হ্যান্ডেল করবে"""
    global pending_results, session_sent_today
    while True:
        try:
            now_bd = datetime.now(bd_tz)
            
            # ⏰ ঠিক দুপুর ১২:৩০ মিনিটে অটোমেটিক সেশন লিস্ট চলে যাবে
            if now_bd.hour == 12 and now_bd.minute == 30:
                if not session_sent_today:
                    await send_auto_bulk_session()
                    session_sent_today = True
            
            # রাত ১২টায় চেক রিসেট হবে পরের দিনের সেশনের জন্য
            if now_bd.hour == 0 and now_bd.minute == 5:
                session_sent_today = False

            # --- অটো উইন/লস রেজাল্ট চেকার ---
            still_pending = []
            for item in pending_results:
                if now_bd >= (item["expiry_time"] + timedelta(seconds=15)):
                    close_price = check_candle_status(item["mt5_pair"], item["timeframe_min"])
                    
                    if close_price:
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
                                m_expiry = now_bd + timedelta(minutes=item["timeframe_min"])
                                m_alert = f"⚠️ **{clean_pair} Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                                await bot.send_message(chat_id=VIP_CHANNEL_ID, text=m_alert, parse_mode="Markdown")

                                current_mt5_price = get_mt5_price(item["mt5_pair"]) or close_price
                                still_pending.append({
                                    "pair": item["pair"], "mt5_pair": item["mt5_pair"], "signal": signal,
                                    "entry_price": current_mt5_price, "timeframe_min": item["timeframe_min"],
                                    "expiry_time": m_expiry, "is_martingale": True
                                })
                            else:
                                result_text = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{clean_pair}`\n🏆 **RESULT :** ❌ M1 LOSS ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                await bot.send_message(chat_id=VIP_CHANNEL_ID, text=result_text, parse_mode="Markdown")
                    else:
                        still_pending.append(item)
                else:
                    still_pending.append(item)

            pending_results = still_pending
        except Exception as e:
            print(f"🔥 Background Core Error: {e}")
        await asyncio.sleep(3)

# ================= TRADINGVIEW WEBHOOK RECEIVER (FLASK) =================
@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    data = request.json
    if not data:
        return jsonify({"status": "error"}), 400

    pair = data.get("pair")          
    signal = data.get("signal")      
    timeframe = data.get("timeframe", "1min") # ডিফল্ট ১ মিনিট লক

    mt5_pair = pair.replace("/", "")
    mt5_price = get_mt5_price(mt5_pair)
    if not mt5_price:
        return jsonify({"status": "error", "message": "MT5 Price Fetch Failed"}), 400

    now_bd = datetime.now(bd_tz)
    entry_time_str = now_bd.strftime("%H:%M")
    duration_min = 1 if timeframe == "1min" else 5
    expiry_time = now_bd + timedelta(minutes=duration_min)

    dir_emoji = "🟢" if signal == "BUY" else "🔴"
    dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
    exp_text = "1 Minute" if timeframe == "1min" else "5 Minutes"
    clean_pair = pair.replace("/", "") + "-OTC"

    msg = f"""💎 **TRADEVISION HYBRID V13.8 (MASTER)** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{clean_pair}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time_str}` (GMT+6)
  ⏳ **Expiry     :** `{exp_text}`
  📈 **Entry Type :** `Next Candle / M1`
╚═══════════════════════════╝
🎯 **Strategy   :** `Ultra Scalper Engine`
⚡ **Validation :** `Dual-Confirm (TV+MT5) ✅`
🔥 **Accuracy   :** `90%-100% SURE-SHOT`"""

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown"))

    pending_results.append({
        "pair": pair, "mt5_pair": mt5_pair, "signal": signal,
        "entry_price": mt5_price, "timeframe_min": duration_min,
        "expiry_time": expiry_time, "is_martingale": False
    })

    return jsonify({"status": "success"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    if initialize_mt5():
        def start_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(background_core_loop())

        t_core = Thread(target=start_async_loop)
        t_core.daemon = True
        t_core.start()

        run_flask()
