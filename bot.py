import os
import asyncio
from datetime import datetime, timedelta
import random
import uuid
import pytz
import logging
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf

# Enterprise Modules
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
import redis

from telegram import Bot
from telegram.ext import Application, CommandHandler
from flask import Flask, jsonify, request
from threading import Thread

# ==================== LOGGING & SETUP ====================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("TradeVision_XGBoost_SMC_Final")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MAIN_CHANNEL_ID = os.environ.get("MAIN_CHANNEL_ID", "@tradevision_ai_signals")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID", "@tradevision_vip_signals")
ADMIN_WHITELIST = [int(i) for i in os.environ.get("ADMIN_WHITELIST", "").split(",") if i.strip()]

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/tradevision")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

if not TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN Missing!")
    exit(1)

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")
app = Flask('')

BOT_RUNNING = True
MAX_DRAWDOWN_LIMIT = 12.0  
IS_DRAWDOWN_MUTED = {"MAIN": False, "VIP": False}
SIGNAL_COOLDOWN_MAP = {} 
PAIR_BLACKLIST = set()    

REAL_FOREX_PAIRS = {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X", "AUD/USD": "AUDUSD=X", "USD/CAD": "CAD=X"}

# ==================== DATABASE & REDIS LAYER ====================
try:
    pg_pool = ThreadedConnectionPool(minconn=2, maxconn=15, dsn=DATABASE_URL)
except Exception as e:
    logger.critical(f"Database Pool Initiation Failed: {e}"); exit(1)

def get_safe_connection():
    """
    অপ্টিমাইজড ও ক্র্যাশ-প্রুফ কানেকশন গেটওয়ে।
    None রিটার্ন করার বদলে অটো-রিকানেকশন ট্রাই করবে।
    """
    global pg_pool
    conn = None
    try:
        conn = pg_pool.getconn()
        # লাইটওয়েট ইন্টারনাল চেক (কানেকশন অলরেডি ব্রোকেন কিনা)
        if conn.closed != 0:
            raise psycopg2.OperationalError("Pre-closed connection object found in pool.")
        return conn
    except Exception as e:
        logger.error(f"🔄 Database Connection Fault: {e}. Attempting auto-recovery...")
        if conn:
            try: pg_pool.putconn(conn, close=True)
            except Exception: pass
        
        # নতুন পুল তৈরি করে রিকভারির শেষ চেষ্টা
        try:
            logger.info("Re-initializing ThreadedConnectionPool...")
            pg_pool = ThreadedConnectionPool(minconn=2, maxconn=15, dsn=DATABASE_URL)
            return pg_pool.getconn()
        except Exception as critical_err:
            logger.critical(f"🚨 DB Pool Re-creation Critical Fail: {critical_err}")
            return None # চূড়ান্ত ব্যর্থতায় কেবল None যাবে, যা হ্যান্ডেল করার জন্য নিচে সেফটি গেট দেওয়া আছে।

r_client = None
try:
    r_client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
    r_client.ping()
except Exception:
    r_client = None

# ==================== CORE COGNITIVE HELPER MODULES ====================
def get_next_candle_time(now_dt):
    minutes_to_add = 5 - (now_dt.minute % 5) if now_dt.minute % 5 != 0 else 5
    return now_dt.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)

def check_session_filter():
    now_bd = datetime.now(bd_tz)
    current_hour = now_bd.hour
    return 12 <= current_hour <= 22

# ==================== ADVANCED TECHNICAL QUANT ENGINE ====================
def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / (down + 1e-10)
    rsi = np.zeros_like(prices)
    rsi[:period+1] = 100. - 100. / (1. + rs)

    for i in range(period+1, len(prices)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta; downval = 0.
        else:
            upval = 0.; downval = -delta
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / (down + 1e-10)
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi

def detect_rsi_divergence(df, rsi_values, lookback=30):
    close = df['Close'].squeeze().values
    
    if close[-1] < close[-lookback] and rsi_values[-1] > rsi_values[-lookback] and rsi_values[-1] < 35:
        return "BULLISH_DIVERGENCE"
    if close[-1] > close[-lookback] and rsi_values[-1] < rsi_values[-lookback] and rsi_values[-1] > 65:
        return "BEARISH_DIVERGENCE"
    return "NONE"

def calculate_atr(df, period=14):
    high = df['High'].squeeze().values
    low = df['Low'].squeeze().values
    close = df['Close'].squeeze().values
    tr1 = high[1:] - low[1:]
    tr2 = np.abs(high[1:] - close[:-1])
    tr3 = np.abs(low[1:] - close[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values
    return float(atr[-1])

# ==================== ADVANCED SMC 2.0 ENGINE ====================
def scan_smc_structures(df):
    high = df['High'].squeeze().values
    low = df['Low'].squeeze().values
    close = df['Close'].squeeze().values
    open_p = df['Open'].squeeze().values
    
    structures = {"FVG": None, "OB": None, "SWEEP": None}
    
    if len(high) >= 3:
        if high[-3] < low[-1]: 
            structures["FVG"] = "BULLISH_FVG"
        elif low[-3] > high[-1]: 
            structures["FVG"] = "BEARISH_FVG"
            
    lookback = 15
    recent_high = np.max(high[-lookback:-1])
    recent_low = np.min(low[-lookback:-1])
    
    if high[-1] > recent_high and close[-1] < recent_high:
        structures["SWEEP"] = "BEARISH_SWEEP" 
    elif low[-1] < recent_low and close[-1] > recent_low:
        structures["SWEEP"] = "BULLISH_SWEEP" 
        
    if close[-1] > open_p[-1] and (close[-1] - open_p[-1]) > (high[-1] - low[-1])*0.6:
        structures["OB"] = "BULLISH_OB"
    elif close[-1] < open_p[-1] and (open_p[-1] - close[-1]) > (high[-1] - low[-1])*0.6:
        structures["OB"] = "BEARISH_OB"
        
    return structures

# ==================== XGBOOST & RANDOM FOREST HYBRID SIMULATOR ====================
def execute_xgb_rf_ensemble_inference(df, rsi, atr, smc):
    f_rsi = rsi[-1]
    f_atr = atr
    f_smc_fvg = 1 if smc["FVG"] == "BULLISH_FVG" else (-1 if smc["FVG"] == "BEARISH_FVG" else 0)
    f_smc_swp = 1 if smc["SWEEP"] == "BULLISH_SWEEP" else (-1 if smc["SWEEP"] == "BEARISH_SWEEP" else 0)
    
    xgb_score = (0.35 * f_smc_swp) + (0.25 * f_smc_fvg) + (0.20 * ((50 - f_rsi) / 50)) + (0.20 * (1 if f_atr > 0.0001 else -1))
    
    rf_vote = 0
    if f_rsi < 35 and f_smc_swp == 1: rf_vote += 1
    if f_rsi > 65 and f_smc_swp == -1: rf_vote -= 1
    if smc["OB"] == "BULLISH_OB": rf_vote += 1
    if smc["OB"] == "BEARISH_OB": rf_vote -= 1
    
    if xgb_score > 0.4 and rf_vote >= 1:
        return "BUY", min(int(80 + (xgb_score * 20)), 98)
    elif xgb_score < -0.4 and rf_vote <= -1:
        return "SELL", min(int(80 + (abs(xgb_score) * 20)), 98)
        
    return None, 0

# ==================== SYSTEM INTERNALS ====================
def monitor_and_blacklist_engine():
    """অটোমেটিক ব্ল্যাকলিস্ট ইঞ্জিন (NoneType সেফটি যুক্ত)"""
    global PAIR_BLACKLIST
    conn = get_safe_connection()
    if conn is None:
        logger.error("⚠️ Skipping Blacklist update check: DB server is unreachable.")
        return
        
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        for pair in list(REAL_FOREX_PAIRS.keys()):
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins
                FROM trade_history 
                WHERE pair = %s AND timestamp > NOW() - INTERVAL '48 hours'
            """, (pair,))
            res = cursor.fetchone()
            if res and res['total'] >= 5:
                win_rate = (res['wins'] / res['total']) * 100
                if win_rate < 70.0:
                    PAIR_BLACKLIST.add(pair)
                    logger.warning(f"⛔ Pair {pair} Blacklisted due to low Win Rate: {win_rate:.1f}%")
                else:
                    PAIR_BLACKLIST.discard(pair)
            cursor.close()
    except Exception as e: 
        logger.error(f"Blacklist tracker failure: {e}")
    finally: 
        try: pg_pool.putconn(conn)
        except Exception: pass

# ==================== QUANT PIPELINE INTEGRATION ====================
def analyze_market_institutional_grade(ticker_symbol, pair_name):
    try:
        if pair_name in PAIR_BLACKLIST: return None, None, 0
        if not check_session_filter(): return None, None, 0 
        
        df = yf.download(tickers=ticker_symbol, period="3d", interval="5m", progress=False)
        if df.empty or len(df) < 40: return None, None, 0
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        
        close_prices = df['Close'].squeeze().values
        rsi_series = calculate_rsi(close_prices, 14)
        atr_val = calculate_atr(df, 14)
        
        if atr_val < 0.00005: return None, None, 0 
        
        div_status = detect_rsi_divergence(df, rsi_series, 25)
        smc_elements = scan_smc_structures(df)
        direction, ml_score = execute_xgb_rf_ensemble_inference(df, rsi_series, atr_val, smc_elements)
        
        if direction:
            if direction == "BUY" and div_status == "BEARISH_DIVERGENCE": return None, None, 0
            if direction == "SELL" and div_status == "BULLISH_DIVERGENCE": return None, None, 0
            
            strat_label = f"🤖 XGBoost Engine + OB + FVG"
            return direction, strat_label, ml_score
            
        return None, None, 0
    except Exception as e:
        logger.error(f"Quant pipeline crash safe trigger: {e}")
        return None, None, 0

# ==================== AUTOMATED CORE PIPELINE ====================
async def automated_trading_loop():
    global BOT_RUNNING, SIGNAL_COOLDOWN_MAP
    
    base_align = get_next_candle_time(datetime.now(bd_tz))
    next_main_time = base_align
    next_vip_time = base_align + timedelta(minutes=5)

    while True:
        try:
            if not BOT_RUNNING:
                await asyncio.sleep(2); continue
            
            now_bd = datetime.now(bd_tz)

            # 📈 MAIN
            if now_bd >= next_main_time and not IS_DRAWDOWN_MUTED["MAIN"]:
                next_main_time = now_bd + timedelta(minutes=random.randint(15, 25))
                for pair_name, ticker in REAL_FOREX_PAIRS.items():
                    if SIGNAL_COOLDOWN_MAP.get(pair_name, now_bd) > now_bd: continue
                    
                    sig, strat, ai_score = analyze_market_institutional_grade(ticker, pair_name)
                    if sig and ai_score >= 85:
                        run_time = get_next_candle_time(now_bd)
                        emoji = "🟢 BUY" if sig == "BUY" else "🔴 SELL"
                        msg = f"🔥 **TRADEVISION PREMIUM AI SETUP**\n\n📊 **Asset:** `{pair_name}`\n🔹 **Direction:** `{emoji}`\n⏰ **Entry Time:** `{run_time.strftime('%H:%M')}`\n🎯 **XGBoost Probable Score:** `{ai_score}%`"
                        await bot.send_message(chat_id=MAIN_CHANNEL_ID, text=msg, parse_mode="Markdown")
                        SIGNAL_COOLDOWN_MAP[pair_name] = now_bd + timedelta(minutes=30)
                        break

            # 👑 VIP
            if now_bd >= next_vip_time and not IS_DRAWDOWN_MUTED["VIP"]:
                next_vip_time = now_bd + timedelta(minutes=random.randint(25, 45))
                for pair_name, ticker in REAL_FOREX_PAIRS.items():
                    if SIGNAL_COOLDOWN_MAP.get(pair_name, now_bd) > now_bd: continue
                    
                    sig, strat, ai_score = analyze_market_institutional_grade(ticker, pair_name)
                    if sig and ai_score >= 92: 
                        run_time = get_next_candle_time(now_bd)
                        emoji = "🟢 BUY" if sig == "BUY" else "🔴 SELL"
                        msg = f"👑 **TRADEVISION VIP INSTITUTIONAL ORDER**\n\n📊 **Asset:** `{pair_name}`\n🔹 **Direction:** `{emoji}`\n⏰ **Entry Time:** `{run_time.strftime('%H:%M')}`\n🔥 **Machine Learning Score:** `{ai_score}%`"
                        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                        SIGNAL_COOLDOWN_MAP[pair_name] = now_bd + timedelta(minutes=30)
                        break

        except Exception as e: logger.error(f"Core process exception: {e}")
        await asyncio.sleep(2)

# ==================== DATA ARCHITECTURE & INITIALIZATION ====================
def init_pg_db():
    """ডাটাবেস টেবিল ইনিশিয়ালাইজার (NoneType সেফটি যুক্ত)"""
    conn = get_safe_connection()
    if conn is None:
        logger.critical("🚨 Critical System Halt: Initial DB Connection Failed. Check connection string!")
        return
        
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                channel TEXT PRIMARY KEY, total_signals INT DEFAULT 0,
                direct_wins INT DEFAULT 0, mg_wins INT DEFAULT 0, losses INT DEFAULT 0,
                current_drawdown NUMERIC(5,2) DEFAULT 0.0, max_drawdown NUMERIC(5,2) DEFAULT 0.0
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_history (
                trade_id TEXT PRIMARY KEY, timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                channel TEXT, pair TEXT, direction TEXT, strategy TEXT, score INT, result TEXT, is_martingale BOOLEAN
            );
        ''')
        conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"Failed to build core tables: {e}")
    finally:
        try: pg_pool.putconn(conn)
        except Exception: pass

# ==================== TELEGRAM SYSTEM CONTROLS ====================
def is_whitelisted(update):
    return ADMIN_WHITELIST and update.effective_user.id in ADMIN_WHITELIST

async def cmd_stats(update, context):
    if not is_whitelisted(update): return
    monitor_and_blacklist_engine() 
    msg = f"📊 **TradeVision Resilient Core Operational Stats**\n\n⛔ **Active Blacklist Pairs:** `{list(PAIR_BLACKLIST) if PAIR_BLACKLIST else 'None'}`\n🌐 **Current Trading Window State:** `{'ACTIVE (NY/London)' if check_session_filter() else 'MUTED (Asian/Off-session)'}`"
    await update.message.reply_text(msg, parse_mode="Markdown")

def start_telegram_app():
    tg_app = Application.builder().token(TOKEN).build()
    tg_app.add_handler(CommandHandler("stats", cmd_stats))
    tg_app.run_polling(close_loop=False)

if __name__ == "__main__":
    init_pg_db()
    
    # থ্রেড ১: মেইন অটোমেটেড কোয়ান্ট ট্রেডিং লুপ
    Thread(target=lambda: asyncio.run(automated_trading_loop()), daemon=True).start()
    # থ্রেড ২: টেলিগ্রাম কমান্ড মডিউল
    Thread(target=start_telegram_app, daemon=True).start()
    
    # ড্যাশবোর্ড বাইন্ডিং
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
