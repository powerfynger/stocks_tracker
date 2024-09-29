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
from data_handler import JsonDBHandler
from portfolio_manager import TinkoffOrderManager

bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
strategy = MoneyFlowStrategy(query_limit=10)
# strategy = LorentzianClassificationStrategy(query_limit=10)
db_handler = JsonDBHandler(Config.DB_FILE_PATH)
stocks_broker = TinkoffOrderManager(db_filepath="TickersToFigi.json",api_key=Config.TINKOFF_REAL_TOKEN)
stocks_processed = {}
stocks_bought = {}

def get_pretty_from_stock(stock_info: Dict) -> str:
    name = stock_info.get('name')
    ticker = stock_info.get('ticker')
    close = stock_info.get('close')
    score = stock_info.get('score')
    atr = round(stock_info.get('ATR'),2)
    
    msg_text = f"📊 *Сигнал на покупку акции*\n\n" \
            f"Компания: *{name}*\n" \
            f"Тикер: `{ticker}`\n" \
            f"Оценка: *{score}/{strategy.get_maxscore()}*.\n"\
            f"Значение ATR: *{atr}*.\n"\
            f"Цена: *{close}*\n\n" \
    # TODO:
    # Добавить процент уверенности по прохождению пороговых значений индикаторов 
    return msg_text

def get_pretty_from_indicators_stock(stock_info: Dict) -> str:
    indicators = strategy.get_indicators()
    msg_text = f"📊 *Сигнал на покупку акции*\n\n"
    for indicator in indicators:
        msg_text += f"*{indicator}*: {stock_info[indicator]}\n"
    
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
    asyncio.create_task(poll_new_actives(context))

async def list_portfolio_stocks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global stocks_bought
    stocks_bought = stocks_broker.get_portfolio_stocks()
    if not stocks_bought:
        await update.message.reply_text("У вас нет активов в портфеле.")
        return 

    msg_text = "Ваши активы:\n\n"
    keyboard = []
    
    for index, stock in enumerate(stocks_bought):
        if stock['ticker'] == None:
            stock['ticker'] = "Rub"
        stock_info = (
            f"Тикер: *{stock['ticker']}*\n"
            f"Текущая стоимость: *{stock['worth_current']}* руб.\n"
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

async def reset_processed_stocks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global stocks_processed
    stocks_processed = {}
    
    await update.message.reply_text(text="Обновлено")

async def poll_new_actives(bot):
    chat_id = Config.TEST_CHAT_ID
    while True:
        data = strategy.get_data()
        
        for stock_info in data:
            stock_info['ticker'] = stock_info['ticker'].split(":")[-1]
            ticker = stock_info['ticker']
            if ticker in stocks_processed and stock_info['ChaikinMoneyFlow|60'] <= stocks_processed[ticker]['ChaikinMoneyFlow|60']:
                continue
            
            keyboard = [
            [InlineKeyboardButton("Купить", callback_data=f"ask_buy_stock_{ticker}")],
            [InlineKeyboardButton("Отмена", callback_data="cancel_button")],]   
            
            reply_markup = InlineKeyboardMarkup(keyboard)

            msg_text = get_pretty_from_indicators_stock(stock_info)
            stocks_processed[ticker] = {}
            stocks_processed[ticker].update(stock_info)
        
            await bot.send_message(chat_id=chat_id, text=msg_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        
        await asyncio.sleep(60)

async def ask_buy_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split("_")[-1]
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
    atr = stocks_processed[ticker]['ATR']
    money_spent = stocks_broker.buy_stock_now(ticker, quantity, atr)
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
            f"Тикер: *{stocks_bought[stock_index]['ticker']}*\n"
            f"Текущая стоимость: *{stocks_bought[stock_index]['worth_current']}* руб.\n"
            f"Количество: *{stocks_bought[stock_index]['quantity']}* шт.\n"
            f"Текущая прибыль: *{stocks_bought[stock_index]['profit_current']}%*\n"
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
    
    msg_text = f"Вы уверены, что хотите продать *{stocks_bought[stock_index]['ticker']}* с текущей прибылью *{stocks_bought[stock_index]['profit_current']}%*?"
    
    keyboard.append([InlineKeyboardButton(text="Продать", callback_data=f"sell_stock_{stock_index}")])
    keyboard.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_button")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def sell_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    stock_index = int(query.data.split("_")[-1])
    money_spent = stocks_broker.sell_stock_now(stocks_bought[stock_index]['ticker'], stocks_bought[stock_index]['quantity'])

    if money_spent:
        await query.edit_message_text(f"Продажа *{stocks_bought[stock_index]['ticker']}* на сумму *{money_spent}* (руб) успешна совершена.",  parse_mode=ParseMode.MARKDOWN)
    else:
        await query.edit_message_text(f"Не удалось продать *{stocks_bought[stock_index]['ticker']}* на сумму *{money_spent}* (руб).", parse_mode=ParseMode.MARKDOWN)
        
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
    
    
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('list', list_portfolio_stocks_command))
    application.add_handler(CommandHandler('reset', reset_processed_stocks_command))


    application.add_handler(CallbackQueryHandler(ask_sell_stock_button, pattern='^ask_sell_stock_'))
    application.add_handler(CallbackQueryHandler(sell_stock_button, pattern='^sell_stock_'))
    application.add_handler(CallbackQueryHandler(buy_stock_button, pattern='^buy_stock_'))
    application.add_handler(CallbackQueryHandler(ask_buy_stock_button, pattern='^ask_buy_stock_'))
    application.add_handler(CallbackQueryHandler(edit_stock_button, pattern='^edit_stock_'))
    application.add_handler(CallbackQueryHandler(cancel_button, pattern='cancel_button'))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(poll_new_actives(application.bot))
    application.run_polling()

if __name__ == "__main__":
    main()