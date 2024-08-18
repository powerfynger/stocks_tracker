import sys
import os
import asyncio
from data_reciever import get_base_statistics
from datetime import datetime

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

user_states = {}

last_message_id = None

def create_menu():
    keyboard = [
        [InlineKeyboardButton("Получить статистику", callback_data='1')],
    ]
    return InlineKeyboardMarkup(keyboard)


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
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    summary += f"\n\n*Дата обновления: {current_time}*"
    return summary


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_message_id
    menu = create_menu()

    message = await update.message.reply_text('Инициализация...', reply_markup=menu)
    last_message_id = message.message_id  

    asyncio.create_task(check_stat(context))

# Обработчик нажатий на кнопки меню
async def button_handler(update: Update, context):
    query = update.callback_query
    data = query.data

    if data == '1':
        data = get_base_statistics()
        msg_text = get_pretty_from_base_stats(data)
    else:
        text = "Неизвестный выбор"

    menu = create_menu()
    await query.edit_message_text(text=msg_text, reply_markup=menu, parse_mode=ParseMode.MARKDOWN)

    
async def get_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_tg = update.effective_user
    data = get_base_statistics()
    msg_text = get_pretty_from_base_stats(data)
    
        
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_text,
        parse_mode=ParseMode.MARKDOWN
    )

async def check_stat(bot):
    global last_message_id
    chat_id = Config.TEST_CHAT_ID
    menu = create_menu()
    while True:
        data = get_base_statistics()
        if data[0]['relative_volume_intraday|5'] > Config.MIN_RELATIVE_VOLUME_DAY:
            msg_text = get_pretty_from_base_stats(data)
            if last_message_id:
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=last_message_id, text=msg_text, parse_mode=ParseMode.MARKDOWN,reply_markup=menu)
                except Exception as e:
                    print(f"Ошибка при обновлении сообщения: {e}")
            else:
                # Если last_message_id нет, отправляем новое сообщение и сохраняем его ID
                new_message = await bot.send_message(chat_id=chat_id, text=msg_text, parse_mode=ParseMode.MARKDOWN, reply_markup=menu)
                last_message_id = new_message.message_id
        await asyncio.sleep(60)
def main():
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_handler))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(check_stat(application.bot))
    application.run_polling()

if __name__ == "__main__":
    main()