import requests
import pandas as pd

API_KEY = "c1ec4ef642224321b031cf3068178289"

def get_market_data(symbol="EUR/USD"):
    try:
        url = "https://api.twelvedata.com/time_series"

        params = {
            "symbol": symbol,
            "interval": "1min",
            "outputsize": 100,
            "apikey": API_KEY
        }

        response = requests.get(url, params=params)
        data = response.json()

        if "values" not in data:
            print("No Data:", data)
            return None

        df = pd.DataFrame(data["values"])

        df["close"] = df["close"].astype(float)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        return df[::-1]

    except Exception as e:
        print("ERROR:", e)
        return None
        PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "AUD/USD"
]
def generate_signal(df):

    current = df["close"].iloc[-1]
    previous = df["close"].iloc[-2]

    if current > previous:
        signal = "BUY"
    else:
        signal = "SELL"

    return signal, current
    for pair in PAIRS:

    df = get_market_data(pair)

    if df is None:
        continue

    signal, price = generate_signal(df)

    message = f"""
🔥 TRADEVISION VIP SIGNAL

💱 Pair: {pair}
📈 Signal: {signal}

🎯 Entry: {price:.5f}
⏰ Expiry: 5 Minutes

⚡ Confidence: 80%
"""

    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=message
    )
    
