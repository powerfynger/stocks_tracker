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
from data_reciever import MoneyFlowStrategy, LorentzianClassificationStrategy
from data_handler import JsonDBHandler
from portfolio_manager import TinkoffOrderManager

bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
strategy = MoneyFlowStrategy(query_limit=5)
db_handler = JsonDBHandler(Config.DB_FILE_PATH)
stocks_broker = TinkoffOrderManager(db_filepath="TickersToFigi.json",api_key=Config.TINKOFF_REAL_TOKEN)
stocks = []


def get_pretty_from_stock(stock_info: Dict) -> str:
    name = stock_info.get('name')
    ticker = stock_info.get('ticker')
    close = stock_info.get('close')
    score = stock_info.get('score')
    
    msg_text = f"📊 *Сигнал на покупку акции*\n\n" \
            f"Компания: *{name}*\n" \
            f"Тикер: `{ticker}`\n" \
            f"Оценка: *{score}/5*.\n"\
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = await update.message.reply_text('Инициализация...')
    asyncio.create_task(poll_new_data(context))

async def list_portfolio_stocks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global stocks
    stocks = stocks_broker.get_portfolio_stocks()
    if not stocks:
        await update.message.reply_text("У вас нет активов в портфеле.")
        return 

    msg_text = "Ваши активы:\n\n"
    keyboard = []
    
    for index, stock in enumerate(stocks):
        if stock['ticker'] == None:
            stock['ticker'] = "Rub"
        stock_info = (
            f"Тикер: *{stock['ticker']}*\n"
            f"Текущая стоимость: *{stock['worth_current']}* руб.\n"
            f"Стоимость при покупке: *{stock['worth_average']}* руб.\n"
            f"Количество: *{stock['quantity']}* шт.\n"
            f"Текущая прибыль: *{stock['profit_current']}%*\n"
            "------------------------------\n"
        )
        msg_text += stock_info
        
        if stock['ticker'] == "Rub":
            continue
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{stock['ticker']}",
                callback_data=f"edit_stock_{index}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_button")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN,)


async def poll_new_data(bot):
    chat_id = Config.TEST_CHAT_ID
    while True:
        parsed_data = db_handler.get_data()
        data = strategy.get_data()
        
        print(parsed_data)
        for stock_info in data:
            ticker = stock_info['ticker']
            if ticker in parsed_data and stock_info['score'] <= parsed_data['ticer']['score']:
                continue
            
            keyboard = [
            [InlineKeyboardButton("Купить", callback_data=f"ask_buy_stock_{ticker}")],
            [InlineKeyboardButton("Отмена", callback_data="cancel_button")],]   
            
            reply_markup = InlineKeyboardMarkup(keyboard)

            msg_text = get_pretty_from_stock(stock_info)
            db_handler.update_data(ticker, stock_info)
            await bot.send_message(chat_id=chat_id, text=msg_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        
        await asyncio.sleep(60)

async def ask_buy_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split("_")[-1].split(":")[-1]
    for stock_info in strategy.get_data():
        if ticker == stock_info['name']:
            price_for_quantity = stocks_broker.get_info_by_ticker(ticker)['lot'] * stock_info['close']
    
    msg_text = (
        f"Тикер: *{ticker}*\n"
        f"Цена за 1 актив: *{price_for_quantity}* руб.\n"
        f"Значение ATR: *{stock_info['ATR']}*.\n"
        f"Оценка: *{stock_info['score']}/5*.\n"
        "Введите количество активов для покупки"
        )
    
    keyboard =[[InlineKeyboardButton("Отмена", callback_data="cancel_button")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data["action"] = "buy_stock"
    context.user_data["ticker"] = ticker
    
    
    await query.edit_message_text(text=msg_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
      
async def buy_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quantity = int(update.message.text)
    ticker = context.user_data["ticker"]
    money_spent = stocks_broker.buy_stock_now(ticker, quantity)
    msg_text = (
        "*КУПЛЕНО*\n"
        f"Тикер: *{ticker}*\n"
        f"Количество: *{quantity}*\n"
        f"Сумма сделки: *{money_spent}* руб.\n"
    )

    if money_spent:
        await update.message.reply_text(text=msg_text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"Не удалось купить *{ticker}* на сумму *{money_spent}* (руб).", parse_mode=ParseMode.MARKDOWN)
    del context.user_data['ticker']
    del context.user_data['action']
      
async def edit_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    stock_index = int(query.data.split("_")[-1])
    keyboard = []
    
    await query.answer()
    
    msg_text = (
            f"Тикер: *{stocks[stock_index]['ticker']}*\n"
            f"Текущая стоимость: *{stocks[stock_index]['worth_current']}* руб.\n"
            f"Средняя стоимость: *{stocks[stock_index]['worth_average']}* руб.\n"
            f"Количество: *{stocks[stock_index]['quantity']}* шт.\n"
            f"Текущая прибыль: *{stocks[stock_index]['profit_current']}%*\n"
        )

    keyboard.append([InlineKeyboardButton(text="Продать", callback_data=f"ask_sell_stock_{stock_index}")])
    keyboard.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_button")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def ask_sell_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    stock_index = int(query.data.split("_")[-1])
    keyboard = []
    
    await query.answer()
    
    msg_text = f"Вы уверены, что хотите продать *{stocks[stock_index]['ticker']}* с текущей прибылью *{stocks[stock_index]['profit_current']}%*?"
    
    keyboard.append([InlineKeyboardButton(text="Продать", callback_data=f"sell_stock_{stock_index}")])
    keyboard.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_button")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def sell_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    stock_index = int(query.data.split("_")[-1])
    money_spent = stocks_broker.sell_stock_now(stocks[stock_index]['ticker'], stocks[stock_index]['quantity'])

    if money_spent:
        await query.edit_message_text(f"Продажа *{stocks[stock_index]['ticker']}* на сумму *{money_spent}* (руб) успешна совершена.",  parse_mode=ParseMode.MARKDOWN)
    else:
        await query.edit_message_text(f"Не удалось продать *{stocks[stock_index]['ticker']}* на сумму *{money_spent}* (руб).", parse_mode=ParseMode.MARKDOWN)
        
async def cancel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()
    await query.edit_message_text("Вы закрыли меню.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'action' in context.user_data:
        action = context.user_data['action']
        if action == 'buy_stock':
            await buy_stock_button(update, context)

def main():
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    db_handler.clean_data()
    
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('list', list_portfolio_stocks_command))


    application.add_handler(CallbackQueryHandler(ask_sell_stock_button, pattern='^ask_sell_stock_'))
    application.add_handler(CallbackQueryHandler(sell_stock_button, pattern='^sell_stock_'))
    application.add_handler(CallbackQueryHandler(buy_stock_button, pattern='^buy_stock_'))
    application.add_handler(CallbackQueryHandler(ask_buy_stock_button, pattern='^ask_buy_stock_'))
    application.add_handler(CallbackQueryHandler(edit_stock_button, pattern='^edit_stock_'))
    application.add_handler(CallbackQueryHandler(cancel_button, pattern='cancel_button'))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(poll_new_data(application.bot))
    application.run_polling()

if __name__ == "__main__":
    main()