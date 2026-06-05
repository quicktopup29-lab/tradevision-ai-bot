import os
from telegram.ext import Application

TOKEN = os.getenv("BOT_TOKEN")

def main():
    app = Application.builder().token(TOKEN).build()

    print("TradeVision AI Bot Running...")

    app.run_polling()

if __name__ == "__main__":
    main()