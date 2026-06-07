import asyncio
from datetime import datetime, timedelta
import os
import pandas as pd
import pytz
from telegram import Bot
import yfinance as yf

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

# ================= YAHOO FINANCE DATA FETCH =================
def get_yf_market_data(symbol, interval):
    try:
        yf_symbol = symbol.replace("/", "") + "=X"
        yf_interval = "1m" if interval == "1min" else "5m"
        period = "2d" if interval == "1min" else "10d"
        
        df = yf.download(tickers=yf_symbol, period=period, interval=yf_interval, progress=False)
        
        if df.empty or len(df) < 20: 
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        
        df.columns = [str(col).lower() for col in df.columns]
        return df
    except Exception as e:
        print(f"❌ Yahoo Finance Fetch Error for {symbol} ({interval}): {e}")
        return None

# ================= HIGH-SPEED MOMENTUM SIGNAL ENGINE =================
def analyze_market(symbol, timeframe):
    df = get_yf_market_data(symbol, timeframe)
    if df is None or len(df) < 15: return None

    try:
        close = df["close"]
        open_p = df["open"]
        high = df["high"]
        low = df["low"]
        
        current_close = close.iloc[-1]
        current_open = open_p.iloc[-1]
        
        # ক্যান্ডেলের সাইজ বা বডি ক্যালকুলেশন (মোমেন্টাম মাপার জন্য)
        candle_body = abs(current_close - current_open)
        
        # এভারেজ ক্যান্ডেল সাইজ বের করা (Volatility Filter)
        avg_body = abs(close - open_p).rolling(10).mean().iloc[-1]

        direction = None
        score = 0

        # ১ মিনিটের জন্য আল্ট্রা-ফাস্ট প্রাইস অ্যাকশন স্কাল্পিং লজিক
        if timeframe == "1min":
            if current_close > current_open and candle_body > (avg_body * 1.2):
                # স্ট্রং গ্রিন ক্যান্ডেল এবং মোমেন্টাম হাই
                direction = "BUY"
                score = 80
            elif current_close < current_open and candle_body > (avg_body * 1.2):
                # স্ট্রং রেড ক্যান্ডেল এবং মোমেন্টাম হাই
                direction = "SELL"
                score = 80
        
        # ৫ মিনিটের জন্য স্ট্যান্ডার্ড ব্রেকআউট লজিক
        else:
            if current_close > open_p.iloc[-5] and current_close > high.rolling(10).mean().iloc[-2]:
                direction = "BUY"
                score = 90
            elif current_close < open_p.iloc[-5] and current_close < low.rolling(10).mean().iloc[-2]:
                direction = "SELL"
                score = 90

        if not direction: return None

        if score >= 90:
            return {"signal": direction, "confidence": 95, "tier": "VIP", "entry_price": current_close}
        else:
            return {"signal": direction, "confidence": 84, "tier": "FREE", "entry_price": current_close}

    except Exception as e:
        print(f"❌ Engine Error for {symbol} ({timeframe}): {e}")
        return None

# ================= TELEGRAM MESSAGE FORMATTING =================
def format_telegram_message(symbol, signal, confidence, entry_time, timeframe, tier, is_martingale=False):
    dir_emoji = "🟢" if signal == "BUY" else "🔴"
    dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
    exp_text = "1 Minute" if timeframe == "1min" else "5 Minutes"
    
    m_header = "⚠️ [MARTINGALE M1] " if is_martingale else ""
    header = f"💎 **TRADEVISION AI → VIP SURE-SHOT** 💎" if tier == "VIP" else f"📡 **TRADEVISION AI → FREE SIGNAL** 📡"
    strategy = "Fast Momentum Scalping" if timeframe == "1min" else "Institutional Trend Breakout"

    return f"""{m_header}{header}
╔═══════════════════════════╗
  📊 **Asset Pair :** `{symbol}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time}` (GMT+6)
  ⏳ **Expiry     :** `{exp_text}`
  📈 **Entry Type :** `{"Martingale Candle" if is_martingale else "Next Candle"}`
╚═══════════════════════════╝
🎯 *Strategy : {strategy}*
🚀 **STATUS :** `{"MARTINGALE ACTIVE" if is_martingale else "ACTIVE"}`
🤖 *Powered by TradeVision Pro Engine v11.5*"""

# ================= PRO AUTO RESULT & MARTINGALE ENGINE =================
async def check_pending_results():
    global pending_results
    now_bd = datetime.now(bd_tz)
    still_pending = []

    for item in pending_results:
        if "attempt" not in item: item["attempt"] = 0

        # ১ মিনিটের জন্য ১৫ সেকেন্ড বাফার, ৫ মিনিটের জন্য ৩০ সেকেন্ড বাফার
        buffer = 15 if item["timeframe"] == "1min" else 30
        if now_bd >= (item["expiry_time"] + timedelta(seconds=buffer)):
            item["attempt"] += 1
            print(f"🔄 Checking Result for {item['pair']} ({item['timeframe']}) | Attempt: {item['attempt']}...")
            
            df = get_yf_market_data(item["pair"], item["timeframe"])
            if df is not None:
                try:
                    current_close = df["close"].iloc[-1]
                    entry_price = item["entry_price"]
                    signal = item["signal"]
                    
                    is_win = (signal == "BUY" and current_close > entry_price) or (signal == "SELL" and current_close < entry_price)

                    if is_win:
                        msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN!! ✅✅"
                        result_text = f"📊 **TRADEVISION AI → RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair']}`\n🏆 **RESULT :** {msg_type} 🎉\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        await bot.send_message(chat_id=item["channel_id"], text=result_text, parse_mode="Markdown")
                    else:
                        if not item["is_martingale"]:
                            m_duration = 1 if item["timeframe"] == "1min" else 5
                            m_run_time = now_bd
                            m_entry_str = m_run_time.strftime("%H:%M")
                            m_expiry = m_run_time + timedelta(minutes=m_duration)

                            m_alert = f"⚠️ **{item['pair']} Direct Trade missed. Use 1-Step Martingale (M1) NOW!**"
                            await bot.send_message(chat_id=item["channel_id"], text=m_alert, parse_mode="Markdown")

                            still_pending.append({
                                "pair": item["pair"], "signal": signal, "entry_price": current_close,
                                "timeframe": item["timeframe"], "entry_time_str": m_entry_str, 
                                "expiry_time": m_expiry, "channel_id": item["channel_id"], 
                                "is_martingale": True, "attempt": 0
                            })
                        else:
                            result_text = f"📊 **TRADEVISION AI → RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair']}`\n🏆 **RESULT :** ❌ M1 LOSS ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            await bot.send_message(chat_id=item["channel_id"], text=result_text, parse_mode="Markdown")
                except Exception as e:
                    if item["attempt"] < 3: still_pending.append(item)
            else:
                if item["attempt"] < 3: still_pending.append(item)
        else:
            still_pending.append(item)

    pending_results = still_pending

# ================= MAIN ENGINE LOOP =================
async def main():
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
    print("🚀 TRADEVISION AI PRO ENGINE v11.5 STARTED (1M+5M SPEED SCALPER)...")

    while True:
        try:
            now_bd = datetime.now(bd_tz)
            if now_bd.weekday() in [5, 6]:
                await asyncio.sleep(3600)
                continue

            await check_pending_results()

            for timeframe in ["5min", "1min"]:
                for pair in pairs:
                    res = analyze_market(pair, timeframe)
                    if res:
                        signal = res["signal"]
                        tier = res["tier"]
                        entry_price = res["entry_price"]
                        filter_key = f"{tier}_{timeframe.upper()}"

                        if last_signals[filter_key].get(pair) != signal:
                            duration = 5 if timeframe == "5min" else 1
                            if timeframe == "5min":
                                current_minute = now_bd.minute
                                remainder = current_minute % 5
                                minutes_to_add = 5 - remainder
                                run_time = now_bd + timedelta(minutes=minutes_to_add)
                            else:
                                run_time = now_bd + timedelta(minutes=1)

                            entry_time_str = run_time.strftime("%H:%M")
                            expiry_time = run_time + timedelta(minutes=duration)

                            msg = format_telegram_message(pair, signal, res["confidence"], entry_time_str, timeframe, tier)
                            target_channel = VIP_CHANNEL_ID if tier == "VIP" else FREE_CHANNEL_ID
                            
                            try:
                                await bot.send_message(chat_id=target_channel, text=msg, parse_mode="Markdown")
                                last_signals[filter_key][pair] = signal
                                print(f"✅ [{timeframe.upper()}] PRO SIGNAL SENT: {pair}")

                                pending_results.append({
                                    "pair": pair, "signal": signal, "entry_price": entry_price,
                                    "timeframe": timeframe, "entry_time_str": entry_time_str, 
                                    "expiry_time": expiry_time, "channel_id": target_channel, 
                                    "is_martingale": False, "attempt": 0
                                })
                            except Exception as e:
                                print(f"❌ Telegram Error: {e}")
                
                await asyncio.sleep(1)

            print("⏳ Cycle Finished. Waiting 60 seconds...\n")
            await asyncio.sleep(60)

        except Exception as main_err:
            print(f"🔥 CRASH PROTECTED: {main_err}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
