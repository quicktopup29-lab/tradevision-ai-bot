import os
import random
import asyncio
from telegram import Bot

TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")

bot = Bot(token=TOKEN)

pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USDT"]

def generate_signal():
    pair = random.choice(pairs)
    direction = random.choice(["CALL 📈", "PUT 📉"])

    return f"""
📡 TRADEVISION QUOTEX SIGNAL

💱 Pair: {pair}
📊 Direction: {direction}
⏱ Timeframe: 1 MIN

⚡ AI Auto Signal
"""

async def run_bot():
    print("Bot Running...")

    while True:
        msg = generate_signal()
        await bot.send_message(chat_id=GROUP_ID, text=msg)
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(run_bot())