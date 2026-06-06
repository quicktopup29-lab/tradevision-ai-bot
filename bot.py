import requests
import pandas as pd

API_KEY = "c1ec4ef642224321b031cf3068178289"

def get_market_data(symbol="EUR/USD"):
    try:

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 50,
        "apikey": API_KEY
    }

    response = requests.get(url, params=params)
    data = response.json()

    if "values" not in data:
        print("API ERROR:", data)
        return None

    df = pd.DataFrame(data["values"])

    df["close"] = df["close"].astype(float)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df[::-1]

except Exception as e:
    print(e)
    return None
    df = get_market_data(symbol)

if df is None:
    return None

current = df["close"].iloc[-1]
previous = df["close"].iloc[-2]

signal = "BUY" if current > previous else "SELL"

tp1 = round(current * 1.0005, 5)
tp2 = round(current * 1.0010, 5)
sl = round(current * 0.9990, 5)

confidence = 80

return f"""
🔥 TRADEVISION VIP SIGNAL

💱 Pair: {symbol}
📈 Signal: {signal}

🎯 Entry: {current:.5f}
🎯 TP1: {tp1}
🎯 TP2: {tp2}
🛑 SL: {sl}

⏰ Expiry: 5 Minutes

⚡ Confidence: {confidence}%
“””

pairs = [
“EUR/USD”,
“GBP/USD”,
“USD/JPY”,
“AUD/USD”
]
signal = generate_signal(pair)

if signal:

    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=signal
    )

    print(f"✅ Signal Sent: {pair}")

await asyncio.sleep(5)
    chat_id=CHANNEL_ID,
    text="""
🔥 TRADEVISION VIP SIGNAL
...
"""
)