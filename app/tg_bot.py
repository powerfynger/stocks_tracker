import sys
import os
import asyncio
from data_reciever import get_base_statistics

script_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.append(os.path.join(script_dir, '..'))


from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode

from config import Config

bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)

def get_recomendation_str(percantage):
    percantage = float(percantage)
    if percantage > 0.5:
        return "Покупать"
    elif percantage < -0.5:
        return "Продавать"
    else:
        return "Неточно"
def get_pretty_from_base_stats(data):
    summary = "**Топ-10 акций:**\n"
    summary += """
- Цена **выше** EMA10: Указывает на то, что цена актива находится в краткосрочном восходящем тренде.\n
- Цена **ниже** EMA10: Указывает на то, что цена актива находится в краткосрочном нисходящем тренде.\n
-----------------\n
- RSI > 70: Актив считается **перекупленным**.\n
- RSI < 30: Актив считается **перепроданным**.\n
"""
    for stock_data in data:
        summary += f"* **{stock_data['name']}**\n"
        summary += f"    * Рекомендация: {get_recomendation_str(stock_data['Recommend.All'])}\n"
        summary += f"    * Относительный объем: {stock_data['relative_volume_intraday|5']:.2f}\n"
        summary += f"    * RSI(15): {stock_data['RSI|15']:.0f}\n"
        summary += f"    * EMA10|5: {stock_data['EMA10|5']:.0f}\n"
    return summary


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_tg = update.effective_user

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Онлайн.",
    )
async def get_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_tg = update.effective_user
    data = get_base_statistics()
    msg_text = get_pretty_from_base_stats(data)
    
        
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_text,
        parse_mode=ParseMode.MARKDOWN
    )

async def check_stat():
    while True:
        data = get_base_statistics()
        if data[0]['relative_volume_intraday|5'] > Config.MIN_RELATIVE_VOLUME_DAY:
            msg_text = get_pretty_from_base_stats(data)
            await bot.send_message(chat_id=Config.TEST_CHAT_ID, text=msg_text, parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(60)

def main():
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))

    application.add_handler(CommandHandler('stat', get_stat))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(check_stat())
    application.run_polling()

if __name__ == "__main__":
    main()