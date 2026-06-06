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
🚀 TradeVision AI Bot Online

✅ Bot Running Successfully
📡 Railway Connected
🤖 Auto Message Test

Time: Every 5 Minutes
"""
            )

            print("✅ Message Sent Successfully")

        except Exception as e:
            print(f"❌ ERROR: {e}")

        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())