import os
from telegram import Bot

TOKEN = os.getenv("BOT_TOKEN")

def main():
    if not TOKEN:
        print("BOT_TOKEN not found")
        return

    bot = Bot(token=TOKEN)
    print("TradeVision AI Bot Started")

if __name__ == "__main__":
    main()