import os
import asyncio
from datetime import datetime, timedelta
import random
import pytz
import sqlite3
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from telegram import Bot
from telegram.ext import Application, CommandHandler
from flask import Flask
from threading import Thread

# ==================== LOGGING CONFIGURATION ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("TradeVision_Ultimate_Engine")

# ==================== CONFIGURATION (SECURE) ====================
# নিরাপত্তা নিশ্চিত করতে টোকেন সম্পূর্ণ এনভায়রনমেন্ট ভেরিয়েবল থেকে নেওয়া হচ্ছে
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MAIN_CHANNEL_ID = os.environ.get("MAIN_CHANNEL_ID", "@tradevision_ai_signals")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID", "@tradevision_vip_signals")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))  # আপনার পার্সোনাল টেলিগ্রাম আইডি এখানে দিন বা ENV সেট করুন

if not TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN missing in environment variables! Process terminated.")
    exit(1)

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")
app = Flask('')

# গ্লোবাল কন্ট্রোল ভেরিয়েবল
BOT_RUNNING = True
pending_results = []
next_main_signal_time = datetime.now(bd_tz)
next_vip_signal_time = datetime.now(bd_tz)
last_report_date = datetime.now(bd_tz).date()

REAL_FOREX_PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X"
}

# ==================== SQLITE DATABASE SYSTEM (THREAD SAFE) ====================
DB_FILE = "tradevision_stats.db"

def init_db():
    """ডেটাবেস এবং টেবিল তৈরি করার ফাংশন (Direct এবং MG Win ট্র্যাকিং সহ)"""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            channel TEXT PRIMARY KEY,
            signals INTEGER DEFAULT 0,
            direct_wins INTEGER DEFAULT 0,
            mg_wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO stats (channel, signals, direct_wins, mg_wins, losses) VALUES ('MAIN', 0, 0, 0, 0)")
    cursor.execute("INSERT OR IGNORE INTO stats (channel, signals, direct_wins, mg_wins, losses) VALUES ('VIP', 0, 0, 0, 0)")
    conn.commit()
    conn.close()

def update_db_stat(channel, stat_type):
    """থ্রেড-সেফ উপায়ে ডেটাবেস স্ট্যাটস আপডেট"""
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE stats SET {stat_type} = {stat_type} + 1 WHERE channel = ?", (channel,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Database update error: {e}")

def get_db_stats():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stats")
    rows = cursor.fetchall()
    conn.close()
    
    current_stats = {}
    for row in rows:
        current_stats[row[0]] = {
            "signals": row[1], 
            "direct_wins": row[2], 
            "mg_wins": row[3], 
            "losses": row[4]
        }
    return current_stats

def reset_db_stats():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        cursor = conn.cursor()
        cursor.execute("UPDATE stats SET signals = 0, direct_wins = 0, mg_wins = 0, losses = 0")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Database reset error: {e}")

init_db()

# ==================== ADVANCED QUANT INDICATORS ====================
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_adx(df, period=14):
    """ট্রেন্ডের শক্তি পরিমাপের জন্য Average Directional Index (ADX)"""
    high, low, close = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    plus_dm = high.diff().where((high.diff() > low.diff(-1)) & (high.diff() > 0), 0)
    minus_dm = low.diff(-1).where((low.diff(-1) > high.diff()) & (low.diff(-1) > 0), 0)
    
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / (atr + 1e-10))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / (atr + 1e-10))
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10))
    return dx.rolling(window=period).mean()

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """MACD Line এবং Signal Line ক্যালকুলেশন"""
    exp1 = prices.ewm(span=fast, adjust=False).mean()
    exp2 = prices.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def is_market_session_active():
    """লন্ডন বা নিউইয়র্ক সেশন (হাই ভলিউম পিরিয়ড) একটিভ আছে কিনা চেক করার ফিল্টার"""
    now_utc = datetime.now(pytz.utc)
    hour = now_utc.hour
    # লন্ডন সেশন: ০৮:০০ - ১৬:০০ UTC | নিউইয়র্ক সেশন: ১৩:০০ - ২১:০০ UTC
    return (8 <= hour <= 21)

# ==================== ADVANCED QUANT ALGO ENGINE ====================
def score_and_analyze_market(ticker_symbol):
    try:
        df_m5 = yf.download(tickers=ticker_symbol, period="3d", interval="5m", progress=False)
        df_m15 = yf.download(tickers=ticker_symbol, period="5d", interval="15m", progress=False)
        
        if df_m5 is None or df_m5.empty or len(df_m5) < 60 or df_m15.empty:
            return None, None, 0

        if isinstance(df_m5.columns, pd.MultiIndex): df_m5.columns = df_m5.columns.get_level_values(0)
        if isinstance(df_m15.columns, pd.MultiIndex): df_m15.columns = df_m15.columns.get_level_values(0)

        df_m5, df_m15 = df_m5.dropna(), df_m15.dropna()
        close_m5, open_m5 = df_m5['Close'].squeeze(), df_m5['Open'].squeeze()
        high_m5, low_m5 = df_m5['High'].squeeze(), df_m5['Low'].squeeze()
        volume_m5 = df_m5['Volume'].squeeze()

        # ইন্ডিকেটর ক্যালকুলেশন
        ema_20 = close_m5.ewm(span=20, adjust=False).mean()
        ema_50 = close_m5.ewm(span=50, adjust=False).mean()
        rsi_m5 = calculate_rsi(close_m5, 14)
        rsi_m15 = calculate_rsi(df_m15['Close'].squeeze(), 14)
        atr_series = calculate_atr(df_m5, 14)
        adx_series = calculate_adx(df_m5, 14)
        macd_line, signal_line = calculate_macd(close_m5)

        # সর্বশেষ ক্লোজড ক্যান্ডেল ডেটা
        c_close, c_open = float(close_m5.iloc[-2]), float(open_m5.iloc[-2])
        c_high, c_low = float(high_m5.iloc[-2]), float(low_m5.iloc[-2])
        c_rsi5, c_rsi15 = float(rsi_m5.iloc[-2]), float(rsi_m15.iloc[-2])
        c_ema20, c_ema20_prev = float(ema_20.iloc[-2]), float(ema_20.iloc[-3])
        c_ema50, c_ema50_prev = float(ema_50.iloc[-2]), float(ema_50.iloc[-3])
        c_atr = float(atr_series.iloc[-2])
        c_adx = float(adx_series.iloc[-2])
        c_macd, c_macd_prev = float(macd_line.iloc[-2]), float(macd_line.iloc[-3])
        c_sig, c_sig_prev = float(signal_line.iloc[-2]), float(signal_line.iloc[-3])

        # ক্যান্ডেলস্টিক প্যাটার্ন এবং ভলিউম ফিল্টার
        avg_volume = volume_m5.tail(20).mean()
        current_volume = volume_m5.iloc[-2]
        candle_body = abs(c_close - c_open)
        avg_body = abs(close_m5.tail(15).diff()).mean()

        # ভলিটালিটি এবং ভলিউম সেফটি প্রোটেকশন
        if c_atr < (avg_body * 0.4) or c_atr > (avg_body * 3.0) or current_volume < (avg_volume * 0.6):
            return None, None, 0

        score = 0
        direction = None
        strategy_text = ""

        # ক্যান্ডেল প্যাটার্ন ডিটেকশন
        is_bullish_engulfing = (c_close > c_open) and (open_m5.iloc[-3] > close_m5.iloc[-3]) and (c_close >= open_m5.iloc[-3]) and (c_open <= close_m5.iloc[-3])
        is_bearish_engulfing = (c_close < c_open) and (close_m5.iloc[-3] > open_m5.iloc[-3]) and (c_close <= open_m5.iloc[-3]) and (c_open >= close_m5.iloc[-3])

        # ১. RSI Reversal + Volume Confirm (BUY/SELL)
        if (c_rsi5 < 28 and c_rsi15 < 33) and (c_close > c_open or is_bullish_engulfing):
            direction = "BUY"
            strategy_text = "🛡️ Multi-TF RSI Oversold & Volatility Bounce"
            score = 82 + int((30 - c_rsi5) * 1.5)
        elif (c_rsi5 > 72 and c_rsi15 > 67) and (c_close < c_open or is_bearish_engulfing):
            direction = "SELL"
            strategy_text = "🛡️ Multi-TF RSI Overbought & Volatility Reversal"
            score = 82 + int((c_rsi5 - 70) * 1.5)

        # ২. Trend Continuation (EMA + ADX + MACD Confirmation)
        elif c_adx > 25: # স্ট্রং ট্রেন্ড ফিল্টার
            if c_ema20 > c_ema50 and c_close > c_ema20 and c_macd > c_sig:
                direction = "BUY"
                strategy_text = "⚡ ADX Strong Golden Trend Continuation"
                score = 75 + int(c_adx * 0.4)
            elif c_ema20 < c_ema50 and c_close < c_ema20 and c_macd < c_sig:
                direction = "SELL"
                strategy_text = "⚡ ADX Strong Death Trend Continuation"
                score = 75 + int(c_adx * 0.4)

        # সেশন বোনাস স্কোর
        if direction and is_market_session_active():
            score += 5

        score = min(score, 100) # ১০০% এর উপরে যেন স্কোর না যায়
        return direction, strategy_text, score
    except Exception as e:
        logger.error(f"Market Analysis Error [{ticker_symbol}]: {e}")
        return None, None, 0

def verify_5min_result(ticker_symbol, entry_time, expected_direction):
    """৫-মিনিটের নিখুঁত ক্যান্ডেল রেজাল্ট ভেরিফায়ার (Error এর ক্ষেত্রে Safe Mode)"""
    try:
        df = yf.download(tickers=ticker_symbol, period="1d", interval="5m", progress=False)
        if df is None or df.empty: return "ERROR_SKIP"
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        df.index = df.index.tz_convert("Asia/Dhaka")
        target_time_str = entry_time.strftime("%H:%M")
        
        for index, row in df.iterrows():
            if index.strftime("%H:%M") == target_time_str:
                open_p = float(row['Open'].item() if hasattr(row['Open'], 'item') else row['Open'])
                close_p = float(row['Close'].item() if hasattr(row['Close'], 'item') else row['Close'])
                
                if close_p > open_p: actual = "BUY"
                elif close_p < open_p: actual = "SELL"
                else: return "LOSS" # Doji ক্যান্ডেল লস হিসেবে গণ্য হবে সেফটির জন্য
                    
                return "WIN" if actual == expected_direction else "LOSS"
        return "ERROR_SKIP"
    except Exception as e:
        logger.error(f"Result Verification Error: {e}")
        return "ERROR_SKIP"

# ==================== AUTOMATED CORE LOOP ====================
async def main_automated_loop():
    global pending_results, next_main_signal_time, next_vip_signal_time, last_report_date, BOT_RUNNING
    logger.info("🚀 TradeVision Quantum Engine Active with Pro Filters...")
    
    next_main_signal_time = datetime.now(bd_tz) + timedelta(seconds=15)
    next_vip_signal_time = datetime.now(bd_tz) + timedelta(minutes=8)

    while True:
        try:
            if not BOT_RUNNING:
                await asyncio.sleep(5)
                continue

            now_bd = datetime.now(bd_tz)

            # 🕒 রাত ১১:৫৯ মিনিটে অটোমেটিক প্রতিদিনের বিস্তারিত পরিসংখ্যান রিপোর্ট পাঠানো ও ডেটা রিসেট
            if now_bd.hour == 23 and now_bd.minute == 59 and now_bd.date() != last_report_date:
                current_stats = get_db_stats()
                for ch_type, ch_id in [("MAIN", MAIN_CHANNEL_ID), ("VIP", VIP_CHANNEL_ID)]:
                    ch_stats = current_stats[ch_type]
                    total = ch_stats["signals"]
                    d_wins = ch_stats["direct_wins"]
                    m_wins = ch_stats["mg_wins"]
                    losses = ch_stats["losses"]
                    total_wins = d_wins + m_wins
                    win_rate = (total_wins / total * 100) if total > 0 else 0
                    
                    ch_title = "📊 FREE CHANNEL DAILY REPORT" if ch_type == "MAIN" else "📊 VIP SURE-SHOT DAILY REPORT"
                    report_msg = f"""{ch_title}
━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Date: `{now_bd.strftime('%d-%m-%Y')}`

🔹 Total Signals : `{total}`
✅ Direct Wins   : `{d_wins}`
🎯 Martingale Win: `{m_wins}`
❌ Total Losses  : `{losses}`
🔥 Net Win Rate  : `{win_rate:.1f}%`
━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Powered by TradeVision Quant Engine"""
                    try:
                        await bot.send_message(chat_id=ch_id, text=report_msg, parse_mode="Markdown")
                    except Exception as ex:
                        logger.error(f"Failed to send stats report: {ex}")
                
                reset_db_stats()
                last_report_date = now_bd.date()

            # 📊 ১. ফ্রি চ্যানেল সিগন্যাল (হাই কোয়ালিটি ফিল্টারড)
            if now_bd >= next_main_signal_time:
                next_main_signal_time = now_bd + timedelta(minutes=random.randint(20, 35)) # সিগন্যাল ফ্রিকোয়েন্সি অপ্টিমাইজড
                
                best_pair, best_ticker, best_signal, best_strategy, max_score = None, None, None, None, 0
                for pair_name, ticker_sym in REAL_FOREX_PAIRS.items():
                    sig, strat, score = score_and_analyze_market(ticker_sym)
                    if sig and score > max_score:
                        max_score = score
                        best_pair, best_ticker, best_signal, best_strategy = pair_name, ticker_sym, sig, strat
                
                if best_signal and max_score >= 82:  # নুন্যতম কঠোর স্কোর ফিল্টার
                    minutes_to_add = 5 - (now_bd.minute % 5)
                    run_time = now_bd + timedelta(minutes=minutes_to_add)
                    entry_str = run_time.strftime("%H:%M")
                    expiry_t = run_time + timedelta(minutes=5)
                    
                    dir_emoji = "🟢" if best_signal == "BUY" else "🔴"
                    dir_text = "CALL / BUY" if best_signal == "BUY" else "PUT / SELL"
                    
                    msg = f"""💎 **TRADEVISION AI → HIGH QUALITY SIGNAL** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{best_pair}` (Real Market)
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_str}` (GMT+6)
  ⏳ **Expiry     :** `5 Minutes (M5)`
  📈 **Entry Type :** `Next Candle`
╚═══════════════════════════╝
🎯 **Strategy   :** `{best_strategy}`
🔥 **AI Score    :** `{max_score}% Confidence Score`
⚠️ **WARNING :** Avoid trading during heavy news impact."""
                    
                    await bot.send_message(chat_id=MAIN_CHANNEL_ID, text=msg, parse_mode="Markdown")
                    update_db_stat("MAIN", "signals")
                    pending_results.append({
                        "channel": "MAIN", "pair": best_pair, "ticker": best_ticker, 
                        "signal": best_signal, "entry_time": run_time, "expiry_time": expiry_t, "is_martingale": False
                    })

            # 📊 ২. ভিআইপি চ্যানেল সিগন্যাল (আল্ট্রা-কনফার্মড ফিল্টার)
            if now_bd >= next_vip_signal_time:
                next_vip_signal_time = now_bd + timedelta(minutes=random.randint(35, 55))
                
                best_pair, best_ticker, best_signal, best_strategy, max_score = None, None, None, None, 0
                for pair_name, ticker_sym in REAL_FOREX_PAIRS.items():
                    sig, strat, score = score_and_analyze_market(ticker_sym)
                    if sig and score > max_score:
                        max_score = score
                        best_pair, best_ticker, best_signal, best_strategy = pair_name, ticker_sym, sig, strat
                
                if best_signal and max_score >= 88:  # ভিআইপি-র জন্য আরও কড়া রিকোয়ারমেন্ট
                    minutes_to_add = 5 - (now_bd.minute % 5)
                    run_time = now_bd + timedelta(minutes=minutes_to_add)
                    entry_str = run_time.strftime("%H:%M")
                    expiry_t = run_time + timedelta(minutes=5)
                    
                    dir_emoji = "🟢" if best_signal == "BUY" else "🔴"
                    dir_text = "CALL / BUY" if best_signal == "BUY" else "PUT / SELL"
                    
                    msg = f"""💎 **TRADEVISION AI → VIP ULTRA CONFIRM** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{best_pair}` (Real Market)
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_str}` (GMT+6)
  ⏳ **Expiry     :** `5 Minutes (M5)`
  📈 **Entry Type :** `Next Candle`
╚═══════════════════════════╝
🎯 **Strategy   :** `{best_strategy}`
🔥 **AI Score    :** `{max_score}% VIP Confidence Score`
⚠️ **WARNING :** Strictly follow your money management setup."""
                    
                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                    update_db_stat("VIP", "signals")
                    pending_results.append({
                        "channel": "VIP", "pair": best_pair, "ticker": best_ticker, 
                        "signal": best_signal, "entry_time": run_time, "expiry_time": expiry_t, "is_martingale": False
                    })

            # 🎯 ৩. ৫-মিনিট রেজাল্ট চেকার ও ডেটাবেস স্ট্যাটস আপডেট
            still_pending = []
            for item in pending_results:
                if now_bd >= (item["expiry_time"] + timedelta(seconds=12)):
                    target_channel = MAIN_CHANNEL_ID if item["channel"] == "MAIN" else VIP_CHANNEL_ID
                    ch_type = item["channel"]
                    
                    result = verify_5min_result(item["ticker"], item["entry_time"], item["signal"])
                    
                    if result == "ERROR_SKIP":
                        # ডেটা মিসিং বা এরর হলে লস না দেখিয়ে স্কিপ করা হবে
                        logger.warning(f"Skipped result validation for {item['pair']} due to data fetching issue.")
                        continue

                    if result == "WIN":
                        emoji = "🟢" if item["signal"] == "BUY" else "🔴"
                        if item["is_martingale"]:
                            msg_type = "🎯🎯 MARTINGALE M5 WIN!! 🎯🎯"
                            update_db_stat(ch_type, "mg_wins")
                        else:
                            msg_type = "✅✅ DIRECT M5 WIN!! ✅✅"
                            update_db_stat(ch_type, "direct_wins")
                            
                        res_msg = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair']}`\n🏆 **RESULT :** {msg_type}\nℹ️ **Candle Info :** {emoji} Real M5 Market Verified!\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        await bot.send_message(chat_id=target_channel, text=res_msg, parse_mode="Markdown")
                    else:  
                        if not item["is_martingale"]:
                            # 🧠 স্মার্ট মার্টিঙ্গেল ফিল্টার: মার্টিঙ্গেল সিগন্যাল দেওয়ার আগে মার্কেট রি-অ্যানালাইসিস করা হবে
                            m_sig, _, m_score = score_and_analyze_market(item["ticker"])
                            
                            if m_sig == item["signal"] and m_score >= 75: # মার্কেট ট্রেন্ড অনুকূলে থাকলেই শুধু মার্টিঙ্গেল কল যাবে
                                m_expiry = now_bd + timedelta(minutes=5)
                                m_emoji = "🟢" if item["signal"] == "BUY" else "🔴"
                                alert = f"⚠️ **{item['pair']} M5 Direct Missed. Market Filter approves Martingale! Use 1-Step Martingale (M5) NOW! {m_emoji}**"
                                await bot.send_message(chat_id=target_channel, text=alert, parse_mode="Markdown")
                                
                                still_pending.append({
                                    "channel": item["channel"], "pair": item["pair"], "ticker": item["ticker"],
                                    "signal": item["signal"], "entry_time": now_bd, "expiry_time": m_expiry, "is_martingale": True
                                })
                            else:
                                # মার্কেট ঝুঁকিপূর্ণ হলে মার্টিঙ্গেল স্কিপ করে সরাসরি সিস্টেম লস ঘোষণা করা হবে
                                res_msg = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair']}`\n❌ **RESULT :** `DIRECT LOSS (MG FILTER REJECTED SAFE MODE)` ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                await bot.send_message(chat_id=target_channel, text=res_msg, parse_mode="Markdown")
                                update_db_stat(ch_type, "losses")
                        else:
                            res_msg = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair']}`\n❌ **RESULT :** `SYSTEM LOSS (M5 FULL FILTER REJECT)` ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            await bot.send_message(chat_id=target_channel, text=res_msg, parse_mode="Markdown")
                            update_db_stat(ch_type, "losses")
                else:
                    still_pending.append(item)
            pending_results = still_pending

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            
        await asyncio.sleep(3)

# ==================== ADMIN TELEGRAM COMMANDS (WITH AUTH) ====================
def is_admin(update):
    """ইউজার আইডি চেক করে শুধুমাত্র এডমিনকে এক্সেস দেওয়ার ফাংশন"""
    if ADMIN_CHAT_ID == 0: 
        return True # ENV সেট না থাকলে সবাই এক্সেস পাবে (টেস্টিং পারপাস)
    return update.effective_user.id == ADMIN_CHAT_ID

async def cmd_stats(update, context):
    if not is_admin(update): return
    current_stats = get_db_stats()
    msg = "📊 **CURRENT LIVE STATISTICS (SQLITE)**\n\n"
    for ch, data in current_stats.items():
        total_wins = data['direct_wins'] + data['mg_wins']
        wr = (total_wins / data['signals'] * 100) if data['signals'] > 0 else 0
        msg += f"🔹 **{ch} Channel:**\nTotal: `{data['signals']}` | Direct Win: `{data['direct_wins']}` | MG Win: `{data['mg_wins']}`\nLosses: `{data['losses']}` | WinRate: `{wr:.1f}%`\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_pause(update, context):
    global BOT_RUNNING
    if not is_admin(update): return
    BOT_RUNNING = False
    await update.message.reply_text("⏸️ **Signal generation has been PAUSED safely.**")

async def cmd_resume(update, context):
    global BOT_RUNNING
    if not is_admin(update): return
    BOT_RUNNING = True
    await update.message.reply_text("▶️ **Signal generation has been RESUMED successfully.**")

def start_telegram_admin():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("pause", cmd_pause))
    application.add_handler(CommandHandler("resume", cmd_resume))
    application.run_polling(close_loop=False)

# ==================== KEEP ALIVE FLASK ====================
@app.route('/')
def home(): return f"TradeVision Quantum Engine Pro is Online. Active State: {BOT_RUNNING}"

if __name__ == "__main__":
    # ১. সিগন্যাল কোর লুপ থ্রেড শুরু
    def start_automated_loop_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_automated_loop())

    t_bot = Thread(target=start_automated_loop_thread)
    t_bot.daemon = True
    t_bot.start()

    # ২. এডমিন প্যানেল থ্রেড শুরু
    t_admin = Thread(target=start_telegram_admin)
    t_admin.daemon = True
    t_admin.start()

    # ৩. ফ্ল্যাস্ক ওয়েব সার্ভার রান
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
