from telegram.ext import Application
import os

TOKEN = os.getenv("BOT_TOKEN")

def main():
    if not TOKEN:
        print("BOT_TOKEN not found")
        return

    app = Application.builder().token(TOKEN).build()

    print("TradeVision AI Bot Running...")

    app.run_polling()

if __name__ == "__main__":
    main()