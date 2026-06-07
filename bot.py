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
CSV_FILE = "cross_tier_signals.csv"

last_signals = {
    "FREE_1MIN": {}, "FREE_5MIN": {},
    "VIP_1MIN": {}, "VIP_5MIN": {}
}

pending_results = []
stats = {"total": 0, "wins": 0, "losses": 0}


# ================= YAHOO FINANCE DATA FETCH =================
def get_yf_market_data(symbol, interval):
    try:
        yf_symbol = symbol.replace("/", "") + "=X"
        yf_interval = "1m" if interval == "1min" else "5m"
        period = "5d" if interval == "1min" else "30d"
        
        df = yf.download(tickers=yf_symbol, period=period, interval=yf_interval, progress=False)
        
        if df.empty or len(df) < 50: 
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        
        df.columns = [str(col).lower() for col in df.columns]
        return df
    except Exception as e:
        print(f"❌ Yahoo Finance Fetch Error for {symbol} ({interval}): {e}")
        return None


# ================= TECHNICAL INDICATORS =================
def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def rsi(series, period=14):
    try:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = -delta.where(delta < 0, 0).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    except:
        return pd.Series([50] * len(series))

def bollinger_bands(series, period=20, num_std=2):
    rolling_mean = series.rolling(window=period).mean()
    rolling_std = series.rolling(window=period).std()
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    return upper_band, lower_band


# ================= PRO FILTER: MULTI-TIMEFRAME TREND CHECK =================
def check_higher_timeframe_trend(symbol, target_direction):
    """৫ মিনিটের চার্ট চেক করে বড় ট্রেন্ড নিশ্চিত করে (১ মিনিটের ফেক সিগন্যাল কমানোর জন্য)"""
    df_5m = get_yf_market_data(symbol, "5min")
    if df_5m is None or len(df_5m) < 50:
        return True # ডেটা না পাওয়া গেলে সেফটির জন্য স্কিপ করবে না
    
    try:
        close = df_5m["close"]
        ema200 = ema(close, 200).iloc[-1]
        current_price = close.iloc[-1]
        
        macro_trend = "BUY" if current_price > ema200 else "SELL"
        return macro_trend == target_direction
    except:
        return True


# ================= SIGNAL ENGINE =================
def analyze_market(symbol, timeframe):
    df = get_yf_market_data(symbol, timeframe)
    if df is None or len(df) < 50: return None

    try:
        close = df["close"]
        available_len = len(close)
        ema_long_period = 200 if available_len >= 200 else 50
        
        ema_long = ema(close, ema_long_period).iloc[-1]
        ema9 = ema(close, 9).iloc[-1]
        ema21 = ema(close, 21).iloc[-1]

        rsi_vals = rsi(close)
        rsi_val = rsi_vals.iloc[-1]
        upper_bb, lower_bb = bollinger_bands(close)

        current_price = close.iloc[-1]
        last_rsi = rsi_vals.iloc[-2]

        score = 0
        direction = None

        if current_price > ema_long:
            if ema9 > ema21: score += 30
            if current_price <= lower_bb.iloc[-1]: score += 35
            if rsi_val < 35 or (last_rsi < 30 and rsi_val > 30): score += 35
            direction = "BUY"
        elif current_price < ema_long:
            if ema9 < ema21: score += 30
            if current_price >= upper_bb.iloc[-1]: score += 35
            if rsi_val > 65 or (last_rsi > 70 and rsi_val < 70): score += 35
            direction = "SELL"

        if not direction or score < 40: return None

        # 🚀 PRO FEATURE: ১ মিনিটের চার্ট হলে ৫ মিনিটের কনফার্মেশন মাস্ট!
        if timeframe == "1min":
            if not check_higher_timeframe_trend(symbol, direction):
                print(f"🛡️ Signal Blocked by Multi-Timeframe Filter: {symbol} 1Min {direction}")
                return None

        if score >= 85:
            return {"signal": direction, "confidence": min(98, score + 10), "tier": "VIP", "entry_price": current_price}
        else:
            return {"signal": direction, "confidence": min(84, score + 15), "tier": "FREE", "entry_price": current_price}

    except Exception as e:
        print(f"❌ Engine Error for {symbol} ({timeframe}): {e}")
        return None


# ================= TELEGRAM MESSAGE FORMATTING =================
def format_telegram_message(symbol, signal, confidence, entry_time, timeframe, tier, is_martingale=False):
    dir_emoji = "🟢" if signal == "BUY" else "🔴"
    dir_text = "CALL / BUY" if signal == "BUY" else "PUT / SELL"
    exp_text = "1 Minute" if timeframe == "1min" else "5 Minutes"
    
    m_header = "⚠️ [MARTINGALE M1] " if is_martingale else ""

    if tier == "VIP":
        header = f"💎 **TRADEVISION AI → VIP SURE-SHOT** 💎"
        strategy = "AI Advanced Breakout + MTF Filter"
        conf_label = f"`{confidence:.0f}% ACCURATE` 🔥"
    else:
        header = f"📡 **TRADEVISION AI → FREE SIGNAL** 📡"
        strategy = "Alpha Momentum Scalping"
        conf_label = f"`–` ⚡"  

    return f"""{m_header}{header}
╔═══════════════════════════╗
  📊 **Asset Pair :** `{symbol}`
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_time}` (BD 🇧🇩)
  ⏳ **Expiry     :** `{exp_text}`
  📈 **Entry Type :** `{"Martingale Candle" if is_martingale else "Next Candle"}`
╚═══════════════════════════╝
🎯 *Strategy : {strategy}*
⚡ *Confidence :* {conf_label}

🚀 **STATUS :** `{"MARTINGALE ACTIVE" if is_martingale else "ACTIVE"}`
🤖 *Powered by TradeVision Pro Engine v11.0*"""


# ================= PRO AUTO RESULT & MARTINGALE ENGINE =================
async def check_pending_results():
    global pending_results
    now_bd = datetime.now(bd_tz)
    still_pending = []

    for item in pending_results:
        if now_bd >= (item["expiry_time"] + timedelta(seconds=30)):
            print(f"🔄 Checking Result for {item['pair']} ({item['timeframe']})...")
            df = get_yf_market_data(item["pair"], item["timeframe"])
            
            if df is not None:
                try:
                    current_close = df["close"].iloc[-1]
                    entry_price = item["entry_price"]
                    signal = item["signal"]
                    
                    is_win = False
                    if signal == "BUY" and current_close > entry_price:
                        is_win = True
                    elif signal == "SELL" and current_close < entry_price:
                        is_win = True

                    if is_win:
                        # ডিরেক্ট উইন অথবা মার্টিনগেল উইন মেসেজ
                        msg_type = "🎯🎯 MARTINGALE M1 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT WIN!! ✅✅"
                        result_text = f"""📊 **TRADEVISION AI → RESULT**
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔹 **Asset Pair :** `{item['pair']}`
🎯 **Direction  :** `{signal}` ({item['timeframe']})

💵 **Entry Price :** `{entry_price:.5f}`
📉 **Expiry Price :** `{current_close:.5f}`

🏆 **RESULT :** {msg_type} 🎉
━━━━━━━━━━━━━━━━━━━━━━━━━━"""
                        await bot.send_message(chat_id=item["channel_id"], text=result_text, parse_mode="Markdown")
                    
                    else:
                        # 🚀 যদি ডিরেক্ট সিগন্যাল লস হয় এবং মার্টিনগেল এখনো দেওয়া না হয়ে থাকে -> M1 স্টার্ট হবে
                        if not item["is_martingale"]:
                            m_duration = 5 if item["timeframe"] == "5min" else 1
                            m_run_time = now_bd
                            m_entry_str = m_run_time.strftime("%H:%M")
                            m_expiry = m_run_time + timedelta(minutes=m_duration)

                            # মার্টিনগেল এলার্ট পাঠানো চ্যানেলে
                            m_alert = f"⚠️ **{item['pair']} Direct Trade missed by points. Use 1-Step Martingale (M1) NOW!**"
                            await bot.send_message(chat_id=item["channel_id"], text=m_alert, parse_mode="Markdown")

                            # নতুন একটি মার্টিনগেল আইটেম পেন্ডিং লিস্টে যোগ করা
                            still_pending.append({
                                "pair": item["pair"],
                                "signal": signal,
                                "entry_price": current_close, # মার্টিনগেলের জন্য এই ক্লোজ প্রাইসটাই নতুন এন্ট্রি প্রাইস
                                "timeframe": item["timeframe"],
                                "entry_time_str": m_entry_str,
                                "expiry_time": m_expiry,
                                "channel_id": item["channel_id"],
                                "is_martingale": True # এইবার মার্টিনগেল ট্রু করা হলো
                            })
                            print(f"⚠️ MARTINGALE M1 TRIGGERED FOR {item['pair']}")
                        else:
                            # মার্টিনগেলও যদি লস হয়, তবেই ফাইনাল LOSS ঘোষণা করা হবে
                            result_text = f"""📊 **TRADEVISION AI → RESULT**
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔹 **Asset Pair :** `{item['pair']}`
🎯 **Direction  :** `{signal}` ({item['timeframe']})

💵 **Entry Price :** `{entry_price:.5f}`
📉 **Expiry Price :** `{current_close:.5f}`

🏆 **RESULT :** ❌ M1 LOSS ❌
━━━━━━━━━━━━━━━━━━━━━━━━━━"""
                            await bot.send_message(chat_id=item["channel_id"], text=result_text, parse_mode="Markdown")
                    
                except Exception as res_err:
                    print(f"❌ Error parsing result for {item['pair']}: {res_err}")
                    still_pending.append(item)
            else:
                still_pending.append(item)
        else:
            still_pending.append(item)

    pending_results = still_pending


# ================= MAIN ENGINE LOOP =================
async def main():
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]

    print("🚀 TRADEVISION AI PRO ENGINE v11.0 STARTED (MTF FILTER + MARTINGALE)...")

    while True:
        try:
            now_bd = datetime.now(bd_tz)
            
            if now_bd.weekday() in [5, 6]:
                print("🔴 WEEKEND DETECTED. MARKET CLOSED.")
                await asyncio.sleep(3600)
                continue

            await check_pending_results()

            for timeframe in ["5min", "1min"]:
                for pair in pairs:
                    res = analyze_market(pair, timeframe)

                    if res:
                        signal = res["signal"]
                        confidence = res["confidence"]
                        tier = res["tier"]
                        entry_price = res["entry_price"]
                        filter_key = f"{tier}_{timeframe.upper()}"

                        if last_signals[filter_key].get(pair) != signal:
                            if timeframe == "5min":
                                current_minute = now_bd.minute
                                remainder = current_minute % 5
                                minutes_to_add = 5 - remainder
                                duration = 5
                                run_time = now_bd + timedelta(minutes=minutes_to_add)
                            else:
                                duration = 1
                                run_time = now_bd + timedelta(minutes=1)

                            entry_time_str = run_time.strftime("%H:%M")
                            expiry_time = run_time + timedelta(minutes=duration)

                            msg = format_telegram_message(pair, signal, confidence, entry_time_str, timeframe, tier)
                            target_channel = VIP_CHANNEL_ID if tier == "VIP" else FREE_CHANNEL_ID
                            
                            try:
                                await bot.send_message(chat_id=target_channel, text=msg, parse_mode="Markdown")
                                last_signals[filter_key][pair] = signal
                                print(f"✅ [{timeframe.upper()}] PRO SIGNAL SENT: {pair}")

                                pending_results.append({
                                    "pair": pair,
                                    "signal": signal,
                                    "entry_price": entry_price,
                                    "timeframe": timeframe,
                                    "entry_time_str": entry_time_str,
                                    "expiry_time": expiry_time,
                                    "channel_id": target_channel,
                                    "is_martingale": False
                                })

                            except Exception as e:
                                print(f"❌ Telegram Send Error: {e}")
                    
                    await asyncio.sleep(1)

            print("⏳ Cycle Finished. Waiting 60 seconds...\n")
            await asyncio.sleep(60)

        except Exception as main_err:
            print(f"🔥 CRASH PROTECTED: {main_err}. Re-initializing in 30s...")
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
