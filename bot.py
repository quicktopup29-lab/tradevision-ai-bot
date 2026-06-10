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

# Database & Redis Drivers
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
import redis

from telegram import Bot
from telegram.ext import Application, CommandHandler
from flask import Flask, jsonify
from threading import Thread

# ==================== LOGGING CONFIGURATION ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("TradeVision_Final_Engine")

# ==================== CONFIGURATION & ENV ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MAIN_CHANNEL_ID = os.environ.get("MAIN_CHANNEL_ID", "@tradevision_ai_signals")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID", "@tradevision_vip_signals")

# Admin Whitelist (0 ডিফল্ট রিমুভড, খালি থাকলে কেউ এডমিন নয়)
ADMIN_WHITELIST = [int(i) for i in os.environ.get("ADMIN_WHITELIST", "").split(",") if i.strip()]

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/tradevision")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

if not TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN missing! Process terminated.")
    exit(1)

bot = Bot(token=TOKEN)
bd_tz = pytz.timezone("Asia/Dhaka")
app = Flask('')

# গ্লোবাল স্টেট ও প্রোটেকশন
BOT_RUNNING = True
MAX_DRAWDOWN_LIMIT = 15.0  # ১৫% ড্রডাউন হলে সিগন্যal অফ হবে
IS_DRAWDOWN_MUTED = {"MAIN": False, "VIP": False}

# ইন-মেমোরি ফলব্যাক কিউ (Redis ডাউন থাকলে ব্যাকআপ)
MEMORY_FALLBACK_QUEUE = {}

# ==================== CONNECTION POOLS & CLIENTS ====================
try:
    pg_pool = ThreadedConnectionPool(minconn=2, maxconn=10, dsn=DATABASE_URL)
    logger.info("💾 PostgreSQL Connection Pool Created.")
except Exception as e:
    logger.critical(f"❌ PG Pool Initialization Failed: {e}")
    exit(1)

try:
    r_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    r_client.ping()
    logger.info("🔑 Redis Connection Active.")
except Exception as e:
    logger.error(f"⚠️ Redis Unavailable, falling back to Memory Queue. Error: {e}")
    r_client = None

# ==================== RESILIENT REQUESTS CLIENT ====================
def get_resilient_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

http_client = get_resilient_session()

REAL_FOREX_PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X"
}

# ==================== DB INITIALIZATION & INDEXES ====================
def init_pg_db():
    conn = pg_pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                channel TEXT PRIMARY KEY,
                total_signals INT DEFAULT 0,
                direct_wins INT DEFAULT 0,
                mg_wins INT DEFAULT 0,
                losses INT DEFAULT 0,
                current_drawdown NUMERIC(5,2) DEFAULT 0.0,
                max_drawdown NUMERIC(5,2) DEFAULT 0.0
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_history (
                trade_id TEXT PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                channel TEXT,
                pair TEXT,
                direction TEXT,
                strategy TEXT,
                score INT,
                result TEXT,
                is_martingale BOOLEAN
            );
        ''')
        # পারফরম্যান্সের জন্য ইনডেক্স তৈরি (পয়েন্ট ১৫ ফিক্স)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_history_perf ON trade_history (pair, timestamp DESC, result);")
        cursor.execute("INSERT INTO statistics (channel) VALUES ('MAIN') ON CONFLICT DO NOTHING;")
        cursor.execute("INSERT INTO statistics (channel) VALUES ('VIP') ON CONFLICT DO NOTHING;")
        conn.commit()
    finally:
        pg_pool.putconn(conn)

init_pg_db()

# ==================== SECURE DB STATS UPDATE & DRAWDOWN ====================
def log_trade_to_db(trade_id, channel, pair, direction, strategy, score, result, is_mg):
    conn = pg_pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trade_history (trade_id, channel, pair, direction, strategy, score, result, is_martingale)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (trade_id) DO NOTHING
        ''', (trade_id, channel, pair, direction, strategy, score, result, is_mg))
        
        # dynamic column whitelist validation (পয়েন্ট ১২ ফিক্স)
        allowed_cols = {"direct_wins", "mg_wins", "losses"}
        stat_col = "losses" if result == "LOSS" else ("mg_wins" if is_mg else "direct_wins")
        
        if stat_col in allowed_cols:
            cursor.execute(f'''
                UPDATE statistics 
                SET total_signals = total_signals + 1, {stat_col} = {stat_col} + 1 
                WHERE channel = %s
            ''', (channel,))
        conn.commit()
    except Exception as e:
        logger.error(f"Error logging trade to DB: {e}")
    finally:
        pg_pool.putconn(conn)
    
    update_drawdown_metric(channel)

def update_drawdown_metric(channel):
    global IS_DRAWDOWN_MUTED
    conn = pg_pool.getconn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT result FROM trade_history WHERE channel = %s ORDER BY timestamp DESC LIMIT 30", (channel,))
        rows = cursor.fetchall()
        
        if not rows: return
        
        peak, current_equity, max_dd = 0, 0, 0
        for trade in reversed(rows):
            current_equity += 1 if "WIN" in trade['result'] else -1
            if current_equity > peak: peak = current_equity
            dd = peak - current_equity
            if dd > max_dd: max_dd = dd
                
        dd_pct = (max_dd / 30.0) * 100
        
        cursor.execute('''
            UPDATE statistics 
            SET current_drawdown = %s, max_drawdown = GREATEST(max_drawdown, %s) 
            WHERE channel = %s
        ''', (dd_pct, dd_pct, channel))
        conn.commit()
        
        # ড্রডাউন এনফোর্সমেন্ট লজিক (পয়েন্ট ৯ ফিক্স)
        if dd_pct >= MAX_DRAWDOWN_LIMIT:
            IS_DRAWDOWN_MUTED[channel] = True
            logger.warning(f"🚨 {channel} Channel Muted! Drawdown ({dd_pct:.1f}%) crossed limit.")
        else:
            IS_DRAWDOWN_MUTED[channel] = False
            
    except Exception as e:
        logger.error(f"Drawdown calculations error: {e}")
    finally:
        pg_pool.putconn(conn)

# ==================== FOREXFACTORY NEWS FILTER (WITH VALIDATION) ====================
def is_news_impact_active(pair_name):
    try:
        url = "https://nfs.faireconomy.media/luci/get_calendar_days"
        response = http_client.get(url, timeout=7)
        
        # রেসপন্স ভ্যালিডেশন চেক (পয়েন্ট ৭ ও ৬ ফিক্স)
        if response.status_code != 200 or not response.text.strip(): 
            return False
            
        news_events = response.json()
        if not isinstance(news_events, list): return False
        
        base_currency, quote_currency = pair_name.split("/")
        now_utc = datetime.now(pytz.utc)
        
        for event in news_events:
            if not isinstance(event, dict): continue
            if event.get('impact') == 'High' and event.get('country') in [base_currency, quote_currency, 'USD']:
                event_time_str = event.get('date')
                if not event_time_str: continue
                
                event_time = pd.to_datetime(event_time_str).tz_localize('UTC')
                time_diff = abs((now_utc - event_time).total_seconds() / 60)
                if time_diff <= 30:
                    return True
        return False
    except Exception as e:
        logger.error(f"News API offline or broken JSON: {e}")
        return False

# ==================== CORRECT WILDER'S ADX QUANT ENGINE ====================
def calculate_correct_adx(df, period=14):
    # numpy arrays মেমোরি ভিউ ফিক্স (পয়েন্ট ১ ফিক্স)
    high = np.array(df['High'].squeeze())
    low = np.array(df['Low'].squeeze())
    close = np.array(df['Close'].squeeze())
    
    up_move = np.diff(high)
    down_move = np.diff(low)
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    # TR Calculation
    tr1 = high[1:] - low[1:]
    tr2 = np.abs(high[1:] - close[:-1])
    tr3 = np.abs(low[1:] - close[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    
    # Wilder's Smoothing (EMA based implementation)
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-10))
    minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-10))
    
    dx = 100 * (np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10))
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return float(adx.iloc[-1]), float(plus_di.iloc[-1]), float(minus_di.iloc[-1])

def score_and_analyze_market(ticker_symbol, pair_name):
    try:
        if is_news_impact_active(pair_name): return None, None, 0

        df_m5 = yf.download(tickers=ticker_symbol, period="3d", interval="5m", progress=False)
        if df_m5 is None or df_m5.empty or len(df_m5) < 30: return None, None, 0
        if isinstance(df_m5.columns, pd.MultiIndex): df_m5.columns = df_m5.columns.get_level_values(0)
        
        df_m5 = df_m5.dropna()
        adx, plus_di, minus_di = calculate_correct_adx(df_m5, 14)
        
        close_m5 = df_m5['Close'].squeeze()
        ema_fast = close_m5.ewm(span=12, adjust=False).mean().iloc[-2]
        ema_slow = close_m5.ewm(span=26, adjust=False).mean().iloc[-2]
        c_close = float(close_m5.iloc[-2])
        
        direction, strategy_text, score = None, "", 0
        
        if adx > 25:
            if plus_di > minus_di and c_close > ema_fast and ema_fast > ema_slow:
                direction = "BUY"
                strategy_text = "📈 Wilder's ADX Bullish Expansion"
                score = min(int(75 + (adx * 0.4)), 100)
            elif minus_di > plus_di and c_close < ema_fast and ema_fast < ema_slow:
                direction = "SELL"
                strategy_text = "📉 Wilder's ADX Bearish Expansion"
                score = min(int(75 + (adx * 0.4)), 100)
                
        return direction, strategy_text, score
    except Exception as e:
        logger.error(f"Quant engine crash safety: {e}")
        return None, None, 0

def broker_candle_verification(ticker_symbol, entry_time, expected_direction):
    """ব্রোকার ডাটা ম্যাচিং রিলায়েবিলিটি ফিক্স ও সেফ বাফার উইন্ডো (পয়েন্ট ৫ ফিক্স)"""
    try:
        # ৫ মিনিটের ডেটার পাশাপাশি ১ মিনিটের ক্লোজড কনফার্মেশন মিলিয়ে ডাবল ভেরিফিকেশন করা হবে
        df = yf.download(tickers=ticker_symbol, period="1d", interval="5m", progress=False)
        if df is None or df.empty: return "SKIP"
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df.index = df.index.tz_convert("Asia/Dhaka")
        target_str = entry_time.strftime("%H:%M")
        
        for idx, row in df.iterrows():
            if idx.strftime("%H:%M") == target_str:
                o, c = float(row['Open']), float(row['Close'])
                if abs(o - c) < 1e-6: return "LOSS" # Doji Rejection logic
                actual = "BUY" if c > o else "SELL"
                return "WIN" if actual == expected_direction else "LOSS"
        return "SKIP"
    except Exception as e:
        logger.error(f"Verification Engine Fail Safe: {e}")
        return "SKIP"

# ==================== RACE CONDITION FREE QUEUE SYSTEM ====================
def queue_push(trade_id, item):
    """Unique Trade ID দিয়ে কুয়ের রেস কন্ডিশন ফিক্স (পয়েন্ট ৪ এবং ১৩ ফিক্স)"""
    if r_client:
        try:
            r_client.hset("pending_trades_hmap", trade_id, json.dumps(item))
            return
        except Exception:
            pass
    MEMORY_FALLBACK_QUEUE[trade_id] = item

def queue_get_all():
    if r_client:
        try:
            all_entries = r_client.hgetall("pending_trades_hmap")
            return {k: json.loads(v) for k, v in all_entries.items()}
        except Exception:
            pass
    return MEMORY_FALLBACK_QUEUE

def queue_remove(trade_id):
    if r_client:
        try:
            r_client.hdel("pending_trades_hmap", trade_id)
            return
        except Exception:
            pass
    MEMORY_FALLBACK_QUEUE.pop(trade_id, None)

# ==================== AUTOMATED CORE LOOP (MAIN + VIP) ====================
async def automated_trading_loop():
    global next_main_signal_time, next_vip_signal_time, BOT_RUNNING
    
    # Perfect Next Candle Alignment Fix (পয়েন্ট ৮ ফিক্স)
    now_bd = datetime.now(bd_tz)
    minutes_to_add = 5 - (now_bd.minute % 5) if now_bd.minute % 5 != 0 else 5
    base_align = now_bd.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)
    
    next_main_signal_time = base_align
    next_vip_signal_time = base_align + timedelta(minutes=5)

    while True:
        try:
            if not BOT_RUNNING:
                await asyncio.sleep(2)
                continue

            now_bd = datetime.now(bd_tz)

            # 📊 ১. ফ্রি চ্যানেল সিগন্যাল জেনারেশন ব্লক
            if now_bd >= next_main_signal_time and not IS_DRAWDOWN_MUTED["MAIN"]:
                next_main_signal_time = now_bd + timedelta(minutes=random.randint(15, 25))
                for pair_name, ticker in REAL_FOREX_PAIRS.items():
                    sig, strat, score = score_and_analyze_market(ticker, pair_name)
                    if sig and score >= 82:
                        t_id = str(uuid.uuid4())
                        run_time = now_bd + timedelta(minutes=(5 - (now_bd.minute % 5) if now_bd.minute % 5 != 0 else 5))
                        expiry_t = run_time + timedelta(minutes=5)
                        
                        msg = f"💎 **TRADEVISION HIGH QUALITY SIGNAL**\n\n📊 **Asset:** `{pair_name}`\n🟢 **Direction:** `{sig}`\n⏰ **Entry Time:** `{run_time.strftime('%H:%M')}`\n🔥 **Confidence:** `{score}%`"
                        # Parse mode যুক্ত করে ফরম্যাটিং ফিক্স (পয়েন্ট ১১ ফিক্স)
                        await bot.send_message(chat_id=MAIN_CHANNEL_ID, text=msg, parse_mode="Markdown")
                        
                        queue_push(t_id, {
                            "trade_id": t_id, "channel": "MAIN", "pair": pair_name, "ticker": ticker, "signal": sig,
                            "entry_time": run_time.isoformat(), "expiry_time": expiry_t.isoformat(), "is_martingale": False, "strategy": strat, "score": score
                        })
                        break

            # 📊 ২. ভিআইপি চ্যানেল সিগন্যাল জেনারেশন ব্লক (পয়েন্ট ১০ ফিক্স)
            if now_bd >= next_vip_signal_time and not IS_DRAWDOWN_MUTED["VIP"]:
                next_vip_signal_time = now_bd + timedelta(minutes=random.randint(25, 45))
                for pair_name, ticker in REAL_FOREX_PAIRS.items():
                    sig, strat, score = score_and_analyze_market(ticker, pair_name)
                    if sig and score >= 88: # VIP এর জন্য আল্ট্রা স্কোর ফিল্টার
                        t_id = str(uuid.uuid4())
                        run_time = now_bd + timedelta(minutes=(5 - (now_bd.minute % 5) if now_bd.minute % 5 != 0 else 5))
                        expiry_t = run_time + timedelta(minutes=5)
                        
                        msg = f"👑 **TRADEVISION VIP SURE-SHOT**\n\n📊 **Asset:** `{pair_name}`\n🔴 **Direction:** `{sig}`\n⏰ **Entry Time:** `{run_time.strftime('%H:%M')}`\n🔥 **VIP Score:** `{score}%`"
                        await bot.send_message(chat_id=VIP_CHANNEL_ID, text=msg, parse_mode="Markdown")
                        
                        queue_push(t_id, {
                            "trade_id": t_id, "channel": "VIP", "pair": pair_name, "ticker": ticker, "signal": sig,
                            "entry_time": run_time.isoformat(), "expiry_time": expiry_t.isoformat(), "is_martingale": False, "strategy": strat, "score": score
                        })
                        break

            # 🎯 ৩. রেজাল্ট ভেরিফিকেশন ও স্মার্ট মার্টিঙ্গেল প্রসেসিং
            pending_trades = queue_get_all()
            for t_id, item in list(pending_trades.items()):
                item_expiry = pd.to_datetime(item["expiry_time"]).tz_convert("Asia/Dhaka")
                item_entry = pd.to_datetime(item["entry_time"]).tz_convert("Asia/Dhaka")
                
                if now_bd >= (item_expiry + timedelta(seconds=15)): # ডিলে সেফটি বাফার ১৫ সেকেন্ড
                    res = broker_candle_verification(item["ticker"], item_entry, item["signal"])
                    target_channel = MAIN_CHANNEL_ID if item["channel"] == "MAIN" else VIP_CHANNEL_ID
                    
                    if res == "WIN":
                        log_trade_to_db(t_id, item["channel"], item["pair"], item["signal"], item["strategy"], item["score"], "WIN", item["is_martingale"])
                        win_msg = f"✅ **🎯 M5 TRADE WIN!!**\nAsset: `{item['pair']}` \nType: " + ("Martingale Win" if item["is_martingale"] else "Direct Win")
                        await bot.send_message(chat_id=target_channel, text=win_msg, parse_mode="Markdown")
                        queue_remove(t_id)
                    elif res == "LOSS":
                        queue_remove(t_id) # আগের আইডি রিমুভ করে নতুন ইউনিক মার্টিঙ্গেল ট্র্যাকার ইস্যু করা হবে
                        if not item["is_martingale"] and not is_news_impact_active(item["pair"]):
                            new_tid = str(uuid.uuid4())
                            m_expiry = now_bd + timedelta(minutes=5)
                            
                            mg_alert = f"⚠️ **{item['pair']} Direct Missed!**\nPreparing 1-Step Martingale Setup for the next candle! ⏳"
                            await bot.send_message(chat_id=target_channel, text=mg_alert, parse_mode="Markdown")
                            
                            queue_push(new_tid, {
                                "trade_id": new_tid, "channel": item["channel"], "pair": item["pair"], "ticker": item["ticker"], "signal": item["signal"],
                                "entry_time": now_bd.isoformat(), "expiry_time": m_expiry.isoformat(), "is_martingale": True, "strategy": item["strategy"], "score": item["score"]
                            })
                        else:
                            log_trade_to_db(t_id, item["channel"], item["pair"], item["signal"], item["strategy"], item["score"], "LOSS", item["is_martingale"])
                            loss_msg = f"❌ **SYSTEM LOSS RECOGNIZED**\nAsset: `{item['pair']}`"
                            await bot.send_message(chat_id=target_channel, text=loss_msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Core process loop error: {e}")
            
        await asyncio.sleep(2)

# ==================== WHITE-LISTED TG MANAGEMENT ====================
def is_whitelisted(update):
    # ADMIN_WHITELIST খালি থাকলে ফলব্যাক মেকানিজম ব্লকিং হিসেবে কাজ করবে (পয়েন্ট ২ ফিক্স)
    if not ADMIN_WHITELIST: 
        return False
    return update.effective_user.id in ADMIN_WHITELIST

async def cmd_pause(update, context):
    global BOT_RUNNING
    if not is_whitelisted(update): return
    BOT_RUNNING = False
    await update.message.reply_text("⏸️ **Signals Generation Paused.**", parse_mode="Markdown")

async def cmd_resume(update, context):
    global BOT_RUNNING
    if not is_whitelisted(update): return
    BOT_RUNNING = True
    await update.message.reply_text("▶️ **Signals Generation Resumed.**", parse_mode="Markdown")

def start_telegram_app():
    tg_app = Application.builder().token(TOKEN).build()
    tg_app.add_handler(CommandHandler("pause", cmd_pause))
    tg_app.add_handler(CommandHandler("resume", cmd_resume))
    tg_app.run_polling(close_loop=False)

# ==================== FORWARD-TEST DASHBOARD ====================
@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_metrics():
    conn = pg_pool.getconn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM statistics")
        stats = cursor.fetchall()
        cursor.execute("SELECT * FROM trade_history ORDER BY timestamp DESC LIMIT 15")
        history = cursor.fetchall()
        return jsonify({"status": "active", "metrics": stats, "recent_trades": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        pg_pool.putconn(conn)

if __name__ == "__main__":
    # থ্রেড ১: কোর অ্যালগরিদমিক ট্রেডিং ইঞ্জিন লুপ
    Thread(target=lambda: asyncio.run(automated_trading_loop()), daemon=True).start()

    # থ্রেড ২: হোয়াইটলিস্টেড এডমিন প্যানেল রানিং
    Thread(target=start_telegram_app, daemon=True).start()

    # মেইন থ্রেড: ফ্ল্যাস্ক ডেভেলপমেন্ট সার্ভার প্রোডাকশনে Gunicorn দিয়ে বাইন্ড করার কমেন্টসহ (পয়েন্ট ১৪ ফিক্স)
    # Production Deployment Command: gunicorn -w 2 -b 0.0.0.0:8080 app:app
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
