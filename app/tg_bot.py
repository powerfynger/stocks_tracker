import sys
import os
import asyncio
from datetime import datetime
from typing import Dict

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
from data_reciever import MoneyFlowStrategy
from data_handler import DBHandler

bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
strategy = MoneyFlowStrategy(query_limit=5)
db_handler = DBHandler(Config.DB_FILE_PATH)

user_states = {}


def get_pretty_from_stock(stock_info: Dict) -> str:
    name = stock_info.get('name')
    ticker = stock_info.get('ticker')
    close = stock_info.get('close')
    
    msg_text = f"📊 *Сигнал на покупку акции*\n\n" \
            f"Компания: *{name}*\n" \
            f"Тикер: `{ticker}`\n" \
            f"Цена: *{close}*\n\n" \
    # TODO:
    # Добавить процент уверенности по прохождению пороговых значений индикаторов 
    return msg_text


def get_recomendation_str(percantage):
    percantage = float(percantage)
    if percantage > 0.5:
        return "Покупать"
    elif percantage < -0.5:
        return "Продавать"
    else:
        return "Неточно"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = await update.message.reply_text('Инициализация...')
    asyncio.create_task(poll_new_data(context))

async def poll_new_data(bot):
    chat_id = Config.TEST_CHAT_ID
    while True:
        parsed_data = db_handler.get_data()
        data = strategy.get_data()
        
        for stock_info in data:
            ticker = stock_info['ticker']
            if ticker in parsed_data:
                continue
            
            keyboard = [
            [InlineKeyboardButton("Купить", callback_data=f"buy_stock_{ticker}")],
            [InlineKeyboardButton("Отмена", callback_data="cancel_button")],]   
            
            reply_markup = InlineKeyboardMarkup(keyboard)

            msg_text = get_pretty_from_stock(stock_info)
            await bot.send_message(chat_id=chat_id, text=msg_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            
            db_handler.update_data(ticker, stock_info)
        
        await asyncio.sleep(60)

async def buy_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split("_")[-1]  
    # TODO:
    # Тестовая/Реальная покупка
    success = True
    
    if success:
        await query.edit_message_text(f"Покупка *{ticker}* успешна совершена.",  parse_mode=ParseMode.MARKDOWN,)
    else:
        await query.edit_message_text(f"Не удалось купить *{ticker}*.", parse_mode=ParseMode.MARKDOWN,)
        
async def cancel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()
    await query.edit_message_text("Вы закрыли меню.")

def main():
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    db_handler.load_data_from_file()
    
    application.add_handler(CommandHandler('start', start))


    application.add_handler(CallbackQueryHandler(buy_stock_button, pattern='^buy_stock_'))
    application.add_handler(CallbackQueryHandler(cancel_button, pattern='cancel_button'))
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(poll_new_data(application.bot))
    application.run_polling()

if __name__ == "__main__":
    main()