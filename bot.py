import os
import asyncio
from telegram.ext import Application

TOKEN = os.getenv("BOT_TOKEN")

async def main():
    if not TOKEN:
        print("BOT_TOKEN not found!")
        return

    app = Application.builder().token(TOKEN).build()

    print("TradeVision AI Bot Running...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())