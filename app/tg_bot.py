import sys
import os
import asyncio
from datetime import datetime
from typing import Dict
import time

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
from data_reciever import MoneyFlowStrategy, NadarayaWatsonStrategy
# from data_handler import JsonDBHandler
from portfolio_manager import TinkoffOrderManager, TinkoffSandboxOrderManager

bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
# strategy = LorentzianClassificationStrategy(query_limit=10)
stop_trading_flag = False
stocks_broker = TinkoffOrderManager(capital=Config.CAPITAL, db_filepath="TickersToFigiRus.json",api_key=Config.TINKOFF_REAL_TOKEN)
# stocks_broker = TinkoffSandboxOrderManager(capital=Config.CAPITAL, db_filepath="TickersToFigiRus.json",api_key=Config.TINKOFF_REAL_TOKEN)
# strategy = MoneyFlowStrategy(query_limit=100)
strategy = NadarayaWatsonStrategy(tinkObj=stocks_broker, query_limit=100)
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

def get_msg_from_stock(stock_info: Dict) -> str:
    # indicators = strategy.get_indicators()
    msg_text = ""
    for indicator_value in stock_info.items():
        msg_text += f"*{indicator_value[0]}*: {indicator_value[1]}\n"
    
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
    start = time.time()
    global stocks_bought
    stocks_bought = stocks_broker.get_portfolio_stocks()
    print(f"Get portfolio: {time.time() - start}")
    if not stocks_bought:
        await update.message.reply_text("У вас нет активов в портфеле.")
        return 

    msg_text = "Ваши активы:\n\n"
    keyboard = []
    
    for index, stock in enumerate(stocks_bought):
        if stock['ticker'] == None:
            stock['ticker'] = "Rub"
       
        stock_info_str = (
            f"*Текущая стоимость:* {stock['worth_current']} руб.\n"
            f"*Количество:* {stock['quantity']} шт.\n"
            f"*Текущая прибыль:* {stock['profit_current']}%\n"
        )

        if stock['ticker'] == "Rub":
            continue
        
        stock_info = strategy.get_data_stock(stock['ticker'])
        if stock_info:
            stock_info_str += get_msg_from_stock(stock_info)
        msg_text += stock_info_str + "------------------------\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{stock['ticker']}",
                callback_data=f"edit_stock_{index}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_button")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN,)

async def get_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(text=f"Баланс: {stocks_broker.get_balance()}")
async def reset_processed_stocks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global stocks_processed
    stocks_processed = {}
    
    await update.message.reply_text(text="Обновлено")

async def get_potential_actives_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = ""
    for stock in strategy.get_data():
        msg_text += get_msg_from_stock(stock)
    if not msg_text:
        msg_text = "Нет подходящих активов для покупки."
    await update.message.reply_text(text=msg_text, parse_mode=ParseMode.MARKDOWN) 

async def stop_trading_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global stop_trading_flag
    stop_trading_flag = True
    await update.message.reply_text(text="Торговля остоновлена.", parse_mode=ParseMode.MARKDOWN) 

async def poll_bought_actives(bot):
    chat_id = Config.TEST_CHAT_ID
    while True:
        if stop_trading_flag:
            return
        await asyncio.sleep(30)
        
        global stocks_bought
        stocks_bought = stocks_broker.get_portfolio_stocks()
        
        if not stocks_bought:
            continue
        
        for index, stock in enumerate(stocks_bought):
            if stock['ticker'] is None:
                continue
            # print(stock, strategy.check_sell(stock['ticker']))
            if strategy.check_sell(stock['ticker']):
                order_worth = stocks_broker.sell_stock_now(stock['ticker'], stocks_bought[index]['quantity'])
                await bot.send_message(chat_id=chat_id, text=f"Продана {stock['ticker']} на {order_worth} с прибылью *{stock['profit_current']}*", parse_mode=ParseMode.MARKDOWN)

async def poll_new_actives(bot):
    chat_id = Config.TEST_CHAT_ID
    while True:
        if stop_trading_flag:
            return
        
        data = strategy.get_data()
        
        for stock_info in data:
            global stocks_bought
            stocks_bought = stocks_broker.get_portfolio_stocks()
            if len(stocks_bought) >= 12:
                await asyncio.sleep(120)
                continue
            stock_info['ticker'] = stock_info['ticker'].split(":")[-1]
            ticker = stock_info['ticker']

            keyboard = [
            [InlineKeyboardButton("Купить", callback_data=f"ask_buy_stock_{ticker}")],
            [InlineKeyboardButton("Отмена", callback_data="cancel_button")],]   
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            msg_text = f"📊 *Сигнал на покупку акции*\n\n" + get_msg_from_stock(stock_info)

            if stock_info['score'] >= strategy.get_border_score():
                if not is_enough_in_portfolio(ticker):
                    amount = min(stocks_broker.get_balance(), stocks_broker.capital//5)
                    # amount = min(stocks_broker.get_balance(), 2000)
                    print(f"Buying {stock_info['ticker']} {amount}")
                    order_worth = stocks_broker.buy_stock_for_amount(stock_info['ticker'], amount)
                    if type(order_worth) == str:
                        pass
                    elif order_worth > 0:
                        await bot.send_message(chat_id=chat_id, text=f"Куплена {stock_info['ticker']} на {order_worth}", parse_mode=ParseMode.MARKDOWN)
                else:
                    # await bot.send_message(chat_id=chat_id, text=msg_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
                    pass
                        
        await asyncio.sleep(30)

def is_enough_in_portfolio(ticker):
    curr = 0
    for stock in stocks_bought:
        if stock['ticker'] == ticker:
            curr += stock['worth_current']
    if curr >=  Config.CAPITAL//4:
        return True
    return False

async def ask_buy_stock_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split("_")[-1]
    for stock_info in strategy.get_data():
        if ticker == stock_info['name']:
            ticker_info = stocks_broker.get_info_by_ticker(ticker)
            if not ticker_info:
                await query.edit_message_text(text=f"Нет информации об инструменте *{ticker}*", parse_mode=ParseMode.MARKDOWN)
                return
            price_for_quantity = ticker_info['lot'] * stock_info['close']
    
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
    # money_spent = stocks_broker.buy_stock_now(ticker, quantity, atr)
    money_spent = stocks_broker.buy_stock_for_amount(ticker, 300)
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
            return
    print("Handling")
    stock_data = strategy.get_data_stock(update.message.text.upper())
    if stock_data:
        await update.message.reply_text(text=get_msg_from_stock(stock_data[0]), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text=f"Не найден тикер {update.message.text}", parse_mode=ParseMode.MARKDOWN)

    

def main():
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    
    
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('list', list_portfolio_stocks_command))
    application.add_handler(CommandHandler('reset', reset_processed_stocks_command))
    application.add_handler(CommandHandler('info', get_potential_actives_command))
    application.add_handler(CommandHandler('stop', stop_trading_command))
    application.add_handler(CommandHandler('balance', get_balance_command))


    application.add_handler(CallbackQueryHandler(ask_sell_stock_button, pattern='^ask_sell_stock_'))
    application.add_handler(CallbackQueryHandler(sell_stock_button, pattern='^sell_stock_'))
    application.add_handler(CallbackQueryHandler(buy_stock_button, pattern='^buy_stock_'))
    application.add_handler(CallbackQueryHandler(ask_buy_stock_button, pattern='^ask_buy_stock_'))
    application.add_handler(CallbackQueryHandler(edit_stock_button, pattern='^edit_stock_'))
    application.add_handler(CallbackQueryHandler(cancel_button, pattern='cancel_button'))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    global stocks_bought
    stocks_bought = stocks_broker.get_portfolio_stocks()


    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(poll_bought_actives(application.bot))
    loop.create_task(poll_new_actives(application.bot))
    application.run_polling()

if __name__ == "__main__":
    main()
