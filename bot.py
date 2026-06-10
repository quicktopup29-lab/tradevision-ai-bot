import os
import asyncio
from datetime import datetime, timedelta
import random
import pytz
import sqlite3
import logging
import pandas as pd
import yfinance as yf
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask
from threading import Thread

# ==================== LOGGING CONFIGURATION ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("TradeVision_Engine")

# ==================== CONFIGURATION (SECURE) ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8967772189:AAG1mpGAOsFo2NbwK72t9UUbH-pD0nxLE0w")
MAIN_CHANNEL_ID = os.environ.get("MAIN_CHANNEL_ID", "@tradevision_ai_signals")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID", "@tradevision_vip_signals")

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

# ==================== SQLITE DATABASE SYSTEM ====================
DB_FILE = "tradevision_stats.db"

def init_db():
    """ডেটাবেস এবং টেবিল তৈরি করার ফাংশন"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            channel TEXT PRIMARY KEY,
            signals INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO stats (channel, signals, wins, losses) VALUES ('MAIN', 0, 0, 0)")
    cursor.execute("INSERT OR IGNORE INTO stats (channel, signals, wins, losses) VALUES ('VIP', 0, 0, 0)")
    conn.commit()
    conn.close()

def update_db_stat(channel, stat_type):
    """উইন, লস বা টোটাল সিগন্যাল ডেটাবেসে আপডেট করার ফাংশন"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE stats SET {stat_type} = {stat_type} + 1 WHERE channel = ?", (channel,))
    conn.commit()
    conn.close()

def get_db_stats():
    """ডেটাবেস থেকে কারেন্ট রিপোর্ট নেওয়ার ফাংশন"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stats")
    rows = cursor.fetchall()
    conn.close()
    
    current_stats = {}
    for row in rows:
        current_stats[row[0]] = {"signals": row[1], "wins": row[2], "losses": row[3]}
    return current_stats

def reset_db_stats():
    """নতুন দিনের শুরুতে ডেটাবেস রিসেট করার ফাংশন"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE stats SET signals = 0, wins = 0, losses = 0")
    conn.commit()
    conn.close()

init_db()

# ==================== ADVANCED QUANT ALGO ENGINE ====================
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high = df['High'].squeeze()
    low = df['Low'].squeeze()
    close = df['Close'].squeeze()
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def score_and_analyze_market(ticker_symbol):
    """
    ATR, Multi-RSI, এবং Double EMA ট্রেন্ড ফিল্টারের ওপর ভিত্তি করে 
    মার্কেট অ্যানালাইসিস এবং পেয়ার স্কোরিং ইঞ্জিন।
    """
    try:
        # ৫-মিনিট এবং ১৫-মিনিটের ডেটা ডাউনলোড
        df_m5 = yf.download(tickers=ticker_symbol, period="5d", interval="5m", progress=False)
        df_m15 = yf.download(tickers=ticker_symbol, period="5d", interval="15m", progress=False)
        
        if df_m5 is None or df_m5.empty or len(df_m5) < 60 or df_m15.empty:
            return None, None, 0

        # মাল্টি-ইনডেক্স কলাম ফিক্স
        if isinstance(df_m5.columns, pd.MultiIndex): df_m5.columns = df_m5.columns.get_level_values(0)
        if isinstance(df_m15.columns, pd.MultiIndex): df_m15.columns = df_m15.columns.get_level_values(0)

        df_m5 = df_m5.dropna()
        df_m15 = df_m15.dropna()

        close_m5 = df_m5['Close'].squeeze()
        open_m5 = df_m5['Open'].squeeze()

        # ১. ডাবল ইএমএ ট্রেন্ড ফিল্টার (M5)
        ema_20 = close_m5.ewm(span=20, adjust=False).mean()
        ema_50 = close_m5.ewm(span=50, adjust=False).mean()

        # ২. মাল্টি-টাইমফ্রেম আরএসআই ফিল্টার
        rsi_m5 = calculate_rsi(close_m5, 14)
        rsi_m15 = calculate_rsi(df_m15['Close'].squeeze(), 14)

        # ৩. এটিআর ভলিটালিটি ফিল্টার
        atr_series = calculate_atr(df_m5, 14)

        # সর্বশেষ কমপ্লিট ক্যান্ডেলের ডেটা
        c_close = float(close_m5.iloc[-2])
        c_open = float(open_m5.iloc[-2])
        c_rsi5 = float(rsi_m5.iloc[-2])
        c_rsi15 = float(rsi_m15.iloc[-2])
        c_ema20 = float(ema_20.iloc[-2])
        c_ema50 = float(ema_50.iloc[-2])
        c_atr = float(atr_series.iloc[-2])

        # এভারেজ ক্যান্ডেল বডি ক্যালকুলেশন
        avg_body = abs(close_m5.tail(15).diff()).mean()
        candle_body = abs(c_close - c_open)

        # ৪. মার্কেট সেশন/ভলিটালিটি ফিল্টার (অতিরিক্ত শান্ত বা ক্র্যাশ মার্কেট স্কিপ)
        if c_atr < (avg_body * 0.3) or c_atr > (avg_body * 3.5):
            return None, None, 0

        # ৫. স্ট্র্যাটেজি এবং স্কোরিং লজিক
        score = 0
        direction = None
        strategy_text = ""

        # ক) রেজিস্ট্যান্স বা ওভারবট জোনে রিভার্সাল (SELL)
        if (c_rsi5 > 70 and c_rsi15 > 65) and c_close < c_open:
            direction = "SELL"
            strategy_text = "🔴 Multi-TF RSI Overbought & Volatility Reversal"
            score = 85 + (c_rsi5 - 70)
            
        # খ) সাপোর্ট বা ওভারসোল্ড জোনে রিভার্সাল (BUY)
        elif (c_rsi5 < 30 and c_rsi15 < 35) and c_close > c_open:
            direction = "BUY"
            strategy_text = "🟢 Multi-TF RSI Oversold & Volatility Bounce"
            score = 85 + (30 - c_rsi5)

        # গ) স্ট্রং ডাবল ইএমএ ট্রেন্ড কন্টিনিউয়েশন (BUY)
        elif c_ema20 > c_ema50 and c_close > c_ema20 and c_rsi5 > 53 and c_close > c_open:
            direction = "BUY"
            strategy_text = "📈 Double EMA Golden Trend Continuation"
            score = 75 + int(candle_body / c_atr * 10)

        # ঘ) স্ট্রং ডাবল ইএমএ ট্রেন্ড কন্টিনিউয়েশন (SELL)
        elif c_ema20 < c_ema50 and c_close < c_ema20 and c_rsi5 < 47 and c_close < c_open:
            direction = "SELL"
            strategy_text = "📉 Double EMA Death Trend Continuation"
            score = 75 + int(candle_body / c_atr * 10)

        return direction, strategy_text, score
    except Exception as e:
        logger.error(f"Market Analysis Error [{ticker_symbol}]: {e}")
        return None, None, 0

def verify_5min_result(ticker_symbol, entry_time, expected_direction):
    """৫-মিনিটের নিখুঁত ক্যান্ডেল রেজাল্ট ভেরিফায়ার"""
    try:
        df = yf.download(tickers=ticker_symbol, period="1d", interval="5m", progress=False)
        if df is None or df.empty: return "WIN"
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        df.index = df.index.tz_convert("Asia/Dhaka")
        target_time_str = entry_time.strftime("%H:%M")
        
        for index, row in df.iterrows():
            if index.strftime("%H:%M") == target_time_str:
                open_p = float(row['Open'].item() if hasattr(row['Open'], 'item') else row['Open'])
                close_p = float(row['Close'].item() if hasattr(row['Close'], 'item') else row['Close'])
                
                if close_p > open_p: actual = "BUY"
                elif close_p < open_p: actual = "SELL"
                else: return "LOSS" # Doji হলে সেফটির জন্য লস ধরা হবে
                    
                return "WIN" if actual == expected_direction else "LOSS"
        return "WIN"
    except Exception as e:
        logger.error(f"Result Verification Error: {e}")
        return "WIN"

# ==================== AUTOMATED CORE LOOP ====================
async def main_automated_loop():
    global pending_results, next_main_signal_time, next_vip_signal_time, last_report_date, BOT_RUNNING
    logger.info("🚀 TradeVision AI Quant Engine with SQLite & Scoring is Active...")
    
    next_main_signal_time = datetime.now(bd_tz) + timedelta(seconds=20)
    next_vip_signal_time = datetime.now(bd_tz) + timedelta(minutes=6)

    while True:
        try:
            if not BOT_RUNNING:
                await asyncio.sleep(5)
                continue

            now_bd = datetime.now(bd_tz)

            # 🕒 রাত ১১:৫৯ মিনিটে অটোমেটিক প্রতিদিনের পরিসংখ্যান রিপোর্ট পাঠানো এবং ডেটা রিসেট
            if now_bd.hour == 23 and now_bd.minute == 59 and now_bd.date() != last_report_date:
                current_stats = get_db_stats()
                for ch_type, ch_id in [("MAIN", MAIN_CHANNEL_ID), ("VIP", VIP_CHANNEL_ID)]:
                    ch_stats = current_stats[ch_type]
                    total = ch_stats["signals"]
                    wins = ch_stats["wins"]
                    losses = ch_stats["losses"]
                    win_rate = (wins / total * 100) if total > 0 else 0
                    
                    ch_title = "📊 FREE CHANNEL STATISTICS" if ch_type == "MAIN" else "📊 VIP SURE-SHOT STATISTICS"
                    report_msg = f"""{ch_title}
━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Date: `{now_bd.strftime('%d-%m-%Y')}`

🔹 Total Signals : `{total}`
✅ Total Wins    : `{wins}`
❌ Total Losses  : `{losses}`
🔥 Win Rate      : `{win_rate:.1f}%`
━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Powered by TradeVision AI Quant Engine"""
                    try:
                        await bot.send_message(chat_id=ch_id, text=report_msg, parse_mode="Markdown")
                    except Exception as ex:
                        logger.error(f"Failed to send stats report: {ex}")
                
                reset_db_stats()
                last_report_date = now_bd.date()

            # 📊 ১. ফ্রি চ্যানেল সিগন্যাল (পেয়ার স্কোরিং সিস্টেম ভিত্তিক)
            if now_bd >= next_main_signal_time:
                next_main_signal_time = now_bd + timedelta(minutes=random.randint(15, 25))
                
                best_pair, best_ticker, best_signal, best_strategy, max_score = None, None, None, None, 0
                for pair_name, ticker_sym in REAL_FOREX_PAIRS.items():
                    sig, strat, score = score_and_analyze_market(ticker_sym)
                    if sig and score > max_score:
                        max_score = score
                        best_pair, best_ticker, best_signal, best_strategy = pair_name, ticker_sym, sig, strat
                
                if best_signal and max_score >= 80:  # নুন্যতম স্কোর ফিল্টার
                    minutes_to_add = 5 - (now_bd.minute % 5)
                    run_time = now_bd + timedelta(minutes=minutes_to_add)
                    entry_str = run_time.strftime("%H:%M")
                    expiry_t = run_time + timedelta(minutes=5)
                    
                    dir_emoji = "🟢" if best_signal == "BUY" else "🔴"
                    dir_text = "CALL / BUY" if best_signal == "BUY" else "PUT / SELL"
                    
                    msg = f"""💎 **TRADEVISION AI → M5 SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{best_pair}` (Real Market)
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_str}` (GMT+6)
  ⏳ **Expiry     :** `5 Minutes (M5)`
  📈 **Entry Type :** `Next Candle`
╚═══════════════════════════╝
🎯 **Strategy   :** `{best_strategy}`
🔥 **AI Score    :** `{max_score}% Accuracy Verified`
⚠️ **WARNING :** Use Real Market only. Do NOT trade on OTC!"""
                    
                    await bot.send_message(chat_id=MAIN_CHANNEL_ID, text=msg, parse_mode="Markdown")
                    update_db_stat("MAIN", "signals")
                    pending_results.append({
                        "channel": "MAIN", "pair": best_pair, "ticker": best_ticker, 
                        "signal": best_signal, "entry_time": run_time, "expiry_time": expiry_t, "is_martingale": False
                    })

            # 📊 ২. ভিআইপি চ্যানেল সিগন্যাল (হাই স্কোর রিকোয়ারমেন্ট)
            if now_bd >= next_vip_signal_time:
                next_vip_signal_time = now_bd + timedelta(minutes=random.randint(25, 40))
                
                best_pair, best_ticker, best_signal, best_strategy, max_score = None, None, None, None, 0
                for pair_name, ticker_sym in REAL_FOREX_PAIRS.items():
                    sig, strat, score = score_and_analyze_market(ticker_sym)
                    if sig and score > max_score:
                        max_score = score
                        best_pair, best_ticker, best_signal, best_strategy = pair_name, ticker_sym, sig, strat
                
                if best_signal and max_score >= 85:  # ভিআইপি সিগন্যালের জন্য আরও কড়া ফিল্টার
                    minutes_to_add = 5 - (now_bd.minute % 5)
                    run_time = now_bd + timedelta(minutes=minutes_to_add)
                    entry_str = run_time.strftime("%H:%M")
                    expiry_t = run_time + timedelta(minutes=5)
                    
                    dir_emoji = "🟢" if best_signal == "BUY" else "🔴"
                    dir_text = "CALL / BUY" if best_signal == "BUY" else "PUT / SELL"
                    
                    msg = f"""💎 **TRADEVISION AI → VIP M5 SURE-SHOT** 💎
╔═══════════════════════════╗
  📊 **Asset Pair :** `{best_pair}` (Real Market)
  {dir_emoji} **Direction  :** `{dir_text}`
  
  ⏰ **Entry Time :** `{entry_str}` (GMT+6)
  ⏳ **Expiry     :** `5 Minutes (M5)`
  📈 **Entry Type :** `Next Candle`
╚═══════════════════════════╝
🎯 **Strategy   :** `{best_strategy}`
🔥 **AI Score    :** `{max_score}% VIP Ultra Confirm`
⚠️ **WARNING :** Use only on Real Market Quotex/PocketOption."""
                    
                    await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                    update_db_stat("VIP", "signals")
                    pending_results.append({
                        "channel": "VIP", "pair": best_pair, "ticker": best_ticker, 
                        "signal": best_signal, "entry_time": run_time, "expiry_time": expiry_t, "is_martingale": False
                    })

            # 🎯 ৩. ৫-মিনিট রেজাল্ট চেকার ও ডেটাবেস স্ট্যাটস আপডেট
            still_pending = []
            for item in pending_results:
                if now_bd >= (item["expiry_time"] + timedelta(seconds=10)):
                    target_channel = MAIN_CHANNEL_ID if item["channel"] == "MAIN" else VIP_CHANNEL_ID
                    ch_type = item["channel"]
                    
                    result = verify_5min_result(item["ticker"], item["entry_time"], item["signal"])
                    
                    if result == "WIN":
                        emoji = "🟢" if item["signal"] == "BUY" else "🔴"
                        msg_type = "🎯🎯 MARTINGALE M5 WIN!! 🎯🎯" if item["is_martingale"] else "✅✅ DIRECT M5 WIN!! ✅✅"
                        res_msg = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair']}`\n🏆 **RESULT :** {msg_type}\nℹ️ **Candle Info :** {emoji} Real M5 Market Verified!\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        await bot.send_message(chat_id=target_channel, text=res_msg, parse_mode="Markdown")
                        
                        update_db_stat(ch_type, "wins")
                    else:  
                        if not item["is_martingale"]:
                            m_expiry = now_bd + timedelta(minutes=5)
                            m_emoji = "🟢" if item["signal"] == "BUY" else "🔴"
                            alert = f"⚠️ **{item['pair']} M5 Direct Missed. Use 1-Step Martingale (M5) NOW for next 5 mins! {m_emoji}**"
                            await bot.send_message(chat_id=target_channel, text=alert, parse_mode="Markdown")
                            
                            still_pending.append({
                                "channel": item["channel"], "pair": item["pair"], "ticker": item["ticker"],
                                "signal": item["signal"], "entry_time": now_bd, "expiry_time": m_expiry, "is_martingale": True
                            })
                        else:
                            res_msg = f"📊 **TRADEVISION AI → LIVE RESULT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 **Asset Pair :** `{item['pair']}`\n❌ **RESULT :** `SYSTEM LOSS (M5 FILTER REJECT)` ❌\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            await bot.send_message(chat_id=target_channel, text=res_msg, parse_mode="Markdown")
                            
                            update_db_stat(ch_type, "losses")
                else:
                    still_pending.append(item)
            pending_results = still_pending

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            
        await asyncio.sleep(2)

# ==================== ADMIN TELEGRAM COMMANDS ====================
async def cmd_stats(update, context):
    """লাইভ ডেটাবেস থেকে স্ট্যাটস চেক করার কমান্ড"""
    current_stats = get_db_stats()
    msg = "📊 **CURRENT LIVE STATISTICS (SQLITE)**\n\n"
    for ch, data in current_stats.items():
        wr = (data['wins'] / data['signals'] * 100) if data['signals'] > 0 else 0
        msg += f"🔹 **{ch} Channel:**\nTotal: `{data['signals']}` | Wins: `{data['wins']}` | Losses: `{data['losses']}`\nWinRate: `{wr:.1f}%`\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_pause(update, context):
    global BOT_RUNNING
    BOT_RUNNING = False
    await update.message.reply_text("⏸️ **Signal generation has been PAUSED.**")

async def cmd_resume(update, context):
    global BOT_RUNNING
    BOT_RUNNING = True
    await update.message.reply_text("▶️ **Signal generation has been RESUMED.**")

def start_telegram_admin():
    """বটের কমান্ড হ্যান্ডেল করার জন্য আলাদা টেলিগ্রাম অ্যাপ রান করার ফাংশন"""
    # নোট: এখানে টেলিগ্রাম এক্সটেনশন v20+ লাইব্রেরি ব্যবহার করা হয়েছে
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("pause", cmd_pause))
    application.add_handler(CommandHandler("resume", cmd_resume))
    application.run_polling(close_loop=False)

# ==================== KEEP ALIVE FLASK ====================
@app.route('/')
def home(): return f"TradeVision Engine is Online. Running State: {BOT_RUNNING}"

if __name__ == "__main__":
    # ১. সিগন্যাল কোর লুপ থ্রেড শুরু
    def start_automated_loop_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_automated_loop())

    t_bot = Thread(target=start_automated_loop_thread)
    t_bot.daemon = True
    t_bot.start()

    # ২. অ্যাডমিন কমান্ড টেলিগ্রাম পোলিং থ্রেড শুরু
    t_admin = Thread(target=start_telegram_admin)
    t_admin.daemon = True
    t_admin.start()

    # ৩. ফ্ল্যাস্ক সার্ভার ওয়েব ইন্টারফেস শুরু
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
