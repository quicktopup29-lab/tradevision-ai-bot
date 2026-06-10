import os
import asyncio
from datetime import datetime, timedelta
import random
import uuid
import pytz
import logging
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import pandas as pd
import numpy as np
import yfinance as yf

# Database, Redis & Controls
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
import redis

from telegram import Bot
from telegram.ext import Application, CommandHandler
from flask import Flask, jsonify, request
from threading import Thread

# ==================== LOGGING CONFIGURATION ====================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("TradeVision_SMC_AI_Engine")

# ==================== CONFIGURATION ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MAIN_CHANNEL_ID = os.environ.get("MAIN_CHANNEL_ID", "@tradevision_ai_signals")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID", "@tradevision_vip_signals")
ADMIN_WHITELIST = [int(i) for i in os.environ.get("ADMIN_WHITELIST", "").split(",") if i.strip()]

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/tradevision")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

if not TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN missing!")
    exit(1)

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")
app = Flask('')

BOT_RUNNING = True
MAX_DRAWDOWN_LIMIT = 15.0  
IS_DRAWDOWN_MUTED = {"MAIN": False, "VIP": False}
MEMORY_FALLBACK_QUEUE = {}

# পেয়ার লিস্টিং ও কারেন্সি ট্র্যাকিং
REAL_FOREX_PAIRS = {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X", "AUD/USD": "AUDUSD=X", "USD/CAD": "CAD=X"}
CURRENCY_TO_COUNTRY = {"USD": "United States", "EUR": "Euro Zone", "GBP": "United Kingdom", "JPY": "Japan", "AUD": "Australia", "CAD": "Canada"}

# ডাইনামিক ব্যাকটেস্ট উইন রেট রেকর্ডার
DYNAMIC_PAIR_WIN_RATES = {pair: 100.0 for pair in REAL_FOREX_PAIRS.keys()}

# ==================== POSTGRES & REDIS POOLS ====================
try:
    pg_pool = ThreadedConnectionPool(minconn=2, maxconn=12, dsn=DATABASE_URL)
except Exception as e:
    logger.critical(f"DB Pool Crash: {e}"); exit(1)

def get_safe_db_connection():
    try:
        conn = pg_pool.getconn()
        cursor = conn.cursor(); cursor.execute("SELECT 1;"); cursor.close()
        return conn
    except Exception:
        global pg_pool
        pg_pool = ThreadedConnectionPool(minconn=2, maxconn=12, dsn=DATABASE_URL)
        return pg_pool.getconn()

r_client = None
def init_redis():
    global r_client
    try:
        r_client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)
        r_client.ping()
    except Exception:
        r_client = None

init_redis()

# ==================== HELPERS ====================
def get_next_candle_time(now_dt):
    minutes_to_add = 5 - (now_dt.minute % 5) if now_dt.minute % 5 != 0 else 5
    return now_dt.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)

def get_resilient_session():
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
    return session

http_client = get_resilient_session()

# ==================== DB CONFIG ====================
def init_pg_db():
    conn = get_safe_db_connection()
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_perf_v3 ON trade_history (pair, timestamp DESC, result);")
        cursor.execute("INSERT INTO statistics (channel) VALUES ('MAIN') ON CONFLICT DO NOTHING;")
        cursor.execute("INSERT INTO statistics (channel) VALUES ('VIP') ON CONFLICT DO NOTHING;")
        conn.commit()
    finally: pg_pool.putconn(conn)

init_pg_db()

# ==================== SECURE NEWS CALENDAR FILTER ====================
def is_news_impact_active(pair_name):
    try:
        url = "https://nfs.faireconomy.media/luci/get_calendar_days"
        response = http_client.get(url, timeout=7)
        if response.status_code != 200 or not response.text.strip(): return False
        
        news_events = response.json()
        base_currency, quote_currency = pair_name.split("/")
        target_countries = [CURRENCY_TO_COUNTRY.get(base_currency), CURRENCY_TO_COUNTRY.get(quote_currency), "United States"]
        now_utc = datetime.now(pytz.utc)
        
        for event in news_events:
            if event.get('impact') == 'High' and event.get('country') in target_countries:
                event_time_str = event.get('date')
                if not event_time_str: continue
                event_time = pd.to_datetime(event_time_str, utc=True).tz_convert('UTC')
                if abs((now_utc - event_time).total_seconds() / 60) <= 30:
                    return True
        return False
    except Exception as e:
        logger.error(f"News API Skip: {e}")
        return False

# ==================== ALGORITHMIC QUANT & SMC ENGINE ====================
def calculate_adx(df, period=14):
    high, low, close = np.array(df['High'].squeeze()), np.array(df['Low'].squeeze()), np.array(df['Close'].squeeze())
    up_move, down_move = np.diff(high), np.diff(low)
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-10))
    minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-10))
    dx = 100 * (np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10))
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return float(adx.iloc[-1]), float(plus_di.iloc[-1]), float(minus_di.iloc[-1])

def detect_smc_bos_mss(df, lookback=20):
    """Smart Money Concept (BOS/MSS) ব্রেকআউট ডিটেকশন ইঞ্জিন"""
    close = df['Close'].squeeze().tolist()
    high = df['High'].squeeze().tolist()
    low = df['Low'].squeeze().tolist()
    
    recent_highs = max(high[-lookback:-1])
    recent_lows = min(low[-lookback:-1])
    
    last_close = close[-1]
    
    if last_close > recent_highs:
        return "BOS_BULLISH"
    elif last_close < recent_lows:
        return "BOS_BEARISH"
    return "CONSOLIDATION"

def analyze_market_ultra_v3(ticker_symbol, pair_name):
    """Multi-Timeframe + SMC (BOS/MSS) + Volume + AI Scoring Engine"""
    try:
        if is_news_impact_active(pair_name): return None, None, 0
        
        # ১. মাল্টি-টাইমফ্রেম ডেটা ডাউনলোডার মডিউল
        df_m5 = yf.download(tickers=ticker_symbol, period="3d", interval="5m", progress=False)
        df_m15 = yf.download(tickers=ticker_symbol, period="5d", interval="15m", progress=False)
        df_h1 = yf.download(tickers=ticker_symbol, period="15d", interval="1h", progress=False)
        
        if df_m5.empty or df_m15.empty or df_h1.empty or len(df_m5) < 30: return None, None, 0
        
        for df in [df_m5, df_m15, df_h1]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df.dropna(inplace=True)
            
        # ২. Higher Timeframe (H1 + M15) ট্রেন্ড এলাইনমেন্ট ফিল্টার
        close_h1 = df_h1['Close'].squeeze()
        ema_h1 = close_h1.ewm(span=50, adjust=False).mean().iloc[-1]
        h1_trend = "BULLISH" if close_h1.iloc[-1] > ema_h1 else "BEARISH"
        
        close_m15 = df_m15['Close'].squeeze()
        ema_m15 = close_m15.ewm(span=20, adjust=False).mean().iloc[-1]
        m15_trend = "BULLISH" if close_m15.iloc[-1] > ema_m15 else "BEARISH"
        
        # ৩. SMC (BOS / MSS) ডিটেকশন ফিল্টার
        smc_status = detect_smc_bos_mss(df_m5, lookback=20)
        
        # ৪. Volume Confirmation (Volume SMA Filter)
        vol_m5 = df_m5['Volume'].squeeze()
        vol_sma = vol_m5.rolling(window=20).mean().iloc[-1]
        last_vol = vol_m5.iloc[-1]
        volume_confirmed = last_vol > vol_sma
        
        # ৫. Core M5 Strategy Execution
        adx, plus_di, minus_di = calculate_adx(df_m5, 14)
        close_m5 = df_m5['Close'].squeeze()
        ema_fast = close_m5.ewm(span=12, adjust=False).mean().iloc[-2]
        c_close = float(close_m5.iloc[-2])
        
        direction = None
        if adx > 22 and volume_confirmed:
            if plus_di > minus_di and c_close > ema_fast and smc_status == "BOS_BULLISH":
                direction = "BUY"
            elif minus_di > plus_di and c_close < ema_fast and smc_status == "BOS_BEARISH":
                direction = "SELL"
                
        if not direction: return None, None, 0
        
        # ৬. AI Confidence Scoring Matrix (0 - 100)
        ai_score = 60
        if h1_trend == direction: ai_score += 15
        if m15_trend == direction: ai_score += 15
        if adx > 30: ai_score += 10
        
        strategy_text = f"⚡ SMC Order Flow ({smc_status})"
        return direction, strategy_text, ai_score
        
    except Exception as e:
        logger.error(f"Quant Framework Exception: {e}")
        return None, None, 0

# ==================== LIVE HISTORICAL BACKTESTING ENGINE ====================
def run_historical_backtest_sync():
    """৩ দিনের হিস্টোরিকাল ডাটার ওপর স্ট্র্যাটেজি ব্যাকটেস্ট করার ইঞ্জিন থ্রেড"""
    global DYNAMIC_PAIR_WIN_RATES
    logger.info("📊 Executing Automated Walk-Forward Historical Backtest Engine...")
    for pair_name, ticker in REAL_FOREX_PAIRS.items():
        try:
            df = yf.download(tickers=ticker, period="3d", interval="5m", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.dropna()
            
            wins, total = 0, 0
            for i in range(30, len(df) - 1):
                sub_df = df.iloc[:i]
                adx, plus_di, minus_di = calculate_adx(sub_df, 14)
                smc = detect_smc_bos_mss(sub_df, 20)
                
                c_close = sub_df['Close'].squeeze().iloc[-1]
                ema_fast = sub_df['Close'].squeeze().ewm(span=12, adjust=False).mean().iloc[-1]
                
                sig = None
                if adx > 22:
                    if plus_di > minus_di and c_close > ema_fast and smc == "BOS_BULLISH": sig = "BUY"
                    elif minus_di > plus_di and c_close < ema_fast and smc == "BOS_BEARISH": sig = "SELL"
                    
                if sig:
                    total += 1
                    actual_future_close = df['Close'].squeeze().iloc[i+1]
                    actual_direction = "BUY" if actual_future_close > c_close else "SELL"
                    if sig == actual_direction: wins += 1
                    
            if total > 0:
                DYNAMIC_PAIR_WIN_RATES[pair_name] = round((wins / total) * 100, 2)
        except Exception as e:
            logger.error(f"Backtest failed for {pair_name}: {e}")
            
    logger.info(f"📈 Backtest Matrix Updated: {DYNAMIC_PAIR_WIN_RATES}")

async def background_backtest_scheduler():
    while True:
        run_historical_backtest_sync()
        await asyncio.sleep(14400) # প্রতি ৪ ঘন্টা পর পর ব্যাকটেস্ট রান হবে

# ==================== QUEUE SYSTEMS ====================
def queue_push(trade_id, item):
    if r_client:
        try: r_client.hset("pending_trades_v3", trade_id, json.dumps(item)); return
        except Exception: pass
    MEMORY_FALLBACK_QUEUE[trade_id] = item

def queue_get_all():
    if r_client:
        try: return {k: json.loads(v) for k, v in r_client.hgetall("pending_trades_v3").items()}
        except Exception: pass
    return MEMORY_FALLBACK_QUEUE

def queue_remove(trade_id):
    if r_client:
        try: r_client.hdel("pending_trades_v3", trade_id); return
        except Exception: pass
    MEMORY_FALLBACK_QUEUE.pop(trade_id, None)

# ==================== VERIFICATION ENGINE ====================
def broker_candle_verification(ticker_symbol, entry_time, expected_direction):
    try:
        df = yf.download(tickers=ticker_symbol, period="1d", interval="5m", progress=False)
        if df.empty: return "SKIP"
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_convert("Asia/Dhaka")
        target_str = entry_time.strftime("%H:%M")
        
        for idx, row in df.iterrows():
            if idx.strftime("%H:%M") == target_str:
                o, c = float(row['Open']), float(row['Close'])
                if abs(o - c) < 1e-6: return "LOSS"
                actual = "BUY" if c > o else "SELL"
                return "WIN" if actual == expected_direction else "LOSS"
        return "SKIP"
    except Exception: return "SKIP"

# ==================== CORE SIGNAL EXECUTION LOOP ====================
async def automated_trading_loop():
    global BOT_RUNNING
    base_align = get_next_candle_time(datetime.now(bd_tz))
    next_main_time = base_align
    next_vip_time = base_align + timedelta(minutes=5)

    while True:
        try:
            if not BOT_RUNNING:
                await asyncio.sleep(2); continue
            now_bd = datetime.now(bd_tz)

            # 📈 MAIN (ফ্রি) চ্যানেল ব্লক (AI Score >= 75 + Backtest Win Rate >= 65%)
            if now_bd >= next_main_time and not IS_DRAWDOWN_MUTED["MAIN"]:
                next_main_time = now_bd + timedelta(minutes=random.randint(15, 25))
                for pair_name, ticker in REAL_FOREX_PAIRS.items():
                    if DYNAMIC_PAIR_WIN_RATES.get(pair_name, 100.0) < 65.0: continue # কম পারফর্মিং পেয়ার ফিল্টার
                    
                    sig, strat, ai_score = analyze_market_ultra_v3(ticker, pair_name)
                    if sig and ai_score >= 75:
                        t_id = str(uuid.uuid4())
                        run_time = get_next_candle_time(now_bd)
                        expiry_t = run_time + timedelta(minutes=5)
                        
                        emoji = "🟢 BUY" if sig == "BUY" else "🔴 SELL"
                        msg = f"💎 **TRADEVISION A+ SETUP SIGNAL**\n\n📊 **Asset:** `{pair_name}`\n🔹 **Direction:** `{emoji}`\n⏰ **Entry Time:** `{run_time.strftime('%H:%M')}`\n🔥 **AI Quality Score:** `{ai_score}/100`"
                        await bot.send_message(chat_id=MAIN_CHANNEL_ID, text=msg, parse_mode="Markdown")
                        
                        queue_push(t_id, {
                            "trade_id": t_id, "channel": "MAIN", "pair": pair_name, "ticker": ticker, "signal": sig,
                            "entry_time": run_time.isoformat(), "expiry_time": expiry_t.isoformat(), "is_martingale": False, "strategy": strat, "score": ai_score
                        })
                        break

            # 👑 VIP চ্যানেল ব্লক - Ultra Setup Only (AI Score >= 90 + Backtest Win Rate >= 75%)
            if now_bd >= next_vip_time and not IS_DRAWDOWN_MUTED["VIP"]:
                next_vip_time = now_bd + timedelta(minutes=random.randint(25, 45))
                for pair_name, ticker in REAL_FOREX_PAIRS.items():
                    if DYNAMIC_PAIR_WIN_RATES.get(pair_name, 100.0) < 75.0: continue 
                    
                    sig, strat, ai_score = analyze_market_ultra_v3(ticker, pair_name)
                    if sig and ai_score >= 90: # Only Ultra A+ Setup Execution
                        t_id = str(uuid.uuid4())
                        run_time = get_next_candle_time(now_bd)
                        expiry_t = run_time + timedelta(minutes=5)
                        
                        emoji = "🟢 BUY" if sig == "BUY" else "🔴 SELL"
                        msg = f"👑 **TRADEVISION VIP ULTRA SHOT**\n\n📊 **Asset:** `{pair_name}`\n🔹 **Direction:** `{emoji}`\n⏰ **Entry Time:** `{run_time.strftime('%H:%M')}`\n🔥 **AI Accuracy Score:** `{ai_score}/100`"
                        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                        
                        queue_push(t_id, {
                            "trade_id": t_id, "channel": "VIP", "pair": pair_name, "ticker": ticker, "signal": sig,
                            "entry_time": run_time.isoformat(), "expiry_time": expiry_t.isoformat(), "is_martingale": False, "strategy": strat, "score": ai_score
                        })
                        break

            # 🎯 রেজাল্ট ট্র্যাকিং ও ভেরিফিকেশন মডিউল
            pending_trades = queue_get_all()
            for t_id, item in list(pending_trades.items()):
                item_expiry = pd.to_datetime(item["expiry_time"]).tz_convert("Asia/Dhaka")
                item_entry = pd.to_datetime(item["entry_time"]).tz_convert("Asia/Dhaka")
                
                if now_bd >= (item_expiry + timedelta(hours=1)):
                    queue_remove(t_id); continue
                
                if now_bd >= (item_expiry + timedelta(seconds=15)):
                    res = broker_candle_verification(item["ticker"], item_entry, item["signal"])
                    target_channel = MAIN_CHANNEL_ID if item["channel"] == "MAIN" else VIP_CHANNEL_ID
                    
                    if res == "WIN":
                        win_msg = f"✅ **🎯 M5 TRADE WIN!!**\nAsset: `{item['pair']}` \nType: " + ("Martingale Win" if item["is_martingale"] else "Direct Win")
                        await bot.send_message(chat_id=target_channel, text=win_msg, parse_mode="Markdown")
                        queue_remove(t_id)
                    elif res == "LOSS":
                        queue_remove(t_id)
                        if not item["is_martingale"] and not is_news_impact_active(item["pair"]):
                            new_tid = str(uuid.uuid4())
                            m_expiry = now_bd + timedelta(minutes=5)
                            mg_alert = f"⚠️ **{item['pair']} Direct Missed!**\nPreparing 1-Step Martingale Setup! ⏳"
                            await bot.send_message(chat_id=target_channel, text=mg_alert, parse_mode="Markdown")
                            
                            queue_push(new_tid, {
                                "trade_id": new_tid, "channel": item["channel"], "pair": item["pair"], "ticker": item["ticker"], "signal": item["signal"],
                                "entry_time": now_bd.isoformat(), "expiry_time": m_expiry.isoformat(), "is_martingale": True, "strategy": item["strategy"], "score": item["score"]
                            })
                        else:
                            loss_msg = f"❌ **SYSTEM LOSS RECOGNIZED**\nAsset: `{item['pair']}`"
                            await bot.send_message(chat_id=target_channel, text=loss_msg, parse_mode="Markdown")

        except Exception as e: logger.error(f"Loop error: {e}")
        await asyncio.sleep(2)

# ==================== WHITE-LISTED TG COMMANDS ====================
def is_whitelisted(update):
    return ADMIN_WHITELIST and update.effective_user.id in ADMIN_WHITELIST

async def cmd_stats(update, context):
    if not is_whitelisted(update): return
    msg = "📊 **SMC-AI Live Dynamic Win-Rates (3D Backtest)**\n━━━━━━━━━━━━━━━━━━━━\n"
    for pair, wr in DYNAMIC_PAIR_WIN_RATES.items():
        msg += f"🔹 `{pair}`: **{wr}%** " + ("🔥 [Optimal]" if wr >= 75 else "⚠️ [Filter Active]") + "\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

def start_telegram_app():
    tg_app = Application.builder().token(TOKEN).build()
    tg_app.add_handler(CommandHandler("stats", cmd_stats))
    tg_app.run_polling(close_loop=False)

if __name__ == "__main__":
    # ১ম ব্যাকটেস্ট রান করে উইন-রেট ইনিশিয়েট করা হবে
    run_historical_backtest_sync()
    
    # ব্যাকগ্রাউন্ড কোর টাস্ক থ্রেডস
    Thread(target=lambda: asyncio.run(automated_trading_loop()), daemon=True).start()
    Thread(target=lambda: asyncio.run(background_backtest_scheduler()), daemon=True).start()
    Thread(target=start_telegram_app, daemon=True).start()

    # Flask Endpoint Binding
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
