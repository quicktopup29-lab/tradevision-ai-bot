import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

async def main():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN NOT FOUND")
        return

    if not CHANNEL_ID:
        print("❌ TELEGRAM_CHANNEL_ID NOT FOUND")
        return

    bot = Bot(token=TOKEN)

    print("✅ Bot Started Successfully")

    while True:
        try:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text="""
🔥 TRADEVISION VIP SIGNAL

💱 Pair: EUR/USD
📈 Signal: BUY

🎯 Entry: 1.14520
🎯 TP1: 1.14600
🎯 TP2: 1.14700
🛑 SL: 1.14420

⏰ Expiry: 5 Minutes

⚡ Confidence: 87%
"""
            )

            print("✅ Message Sent Successfully")

        except Exception as e:
            print(f"❌ ERROR: {e}")

        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())