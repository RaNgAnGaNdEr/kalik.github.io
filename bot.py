import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
import threading
import asyncio

app = Flask(__name__)

# Настройки
BOT_TOKEN = os.environ.get('BOT_TOKEN')
STAFF_CHAT_ID = os.environ.get('STAFF_CHAT_ID')

if not BOT_TOKEN or not STAFF_CHAT_ID:
    print("⚠️ ВНИМАНИЕ: BOT_TOKEN или STAFF_CHAT_ID не заданы!")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# База данных
def init_db():
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  user_name TEXT,
                  time TEXT,
                  zone TEXT,
                  flavor TEXT,
                  strength INTEGER,
                  drinks TEXT,
                  total_price INTEGER,
                  status TEXT,
                  created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# === КОМАНДЫ ДЛЯ БОТА ===
async def start(update, context):
    await update.message.reply_text("🤖 Бот для приёма заказов работает!\n\nКоманды:\n/status - последние заказы")

async def status(update, context):
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()
    c.execute("SELECT id, user_name, time, total_price, status FROM bookings ORDER BY id DESC LIMIT 5")
    orders = c.fetchall()
    conn.close()
    
    if orders:
        msg = "📋 <b>Последние 5 заказов:</b>\n\n"
        for o in orders:
            msg += f"#{o[0]} | {o[1]} | {o[2]} | {o[3]}₽ | {o[4]}\n"
        await update.message.reply_text(msg, parse_mode='HTML')
    else:
        await update.message.reply_text("📭 Заказов пока нет")

# === API ДЛЯ MINI APP ===
@app.route('/booking', methods=['POST'])
def create_booking():
    try:
        data = request.json
        print(f"📦 Получен заказ: {data}")
        
        conn = sqlite3.connect('bookings.db')
        c = conn.cursor()
        c.execute('''INSERT INTO bookings 
                     (user_id, user_name, time, zone, flavor, strength, drinks, total_price, status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (data.get('user_id', 0), 
                   data.get('user_name', 'Гость'), 
                   data.get('time', ''),
                   data.get('zone', ''),
                   data.get('hookah', {}).get('flavor', ''),
                   data.get('hookah', {}).get('strength', 5),
                   json.dumps(data.get('drinks', [])),
                   data.get('totalPrice', 0),
                   'new', 
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        booking_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Отправляем в Telegram
        if bot and STAFF_CHAT_ID:
            drinks_list = data.get('drinks', [])
            if drinks_list:
                drinks_text = "\n".join([f"• {d['name']} - {d['price']}₽" for d in drinks_list])
            else:
                drinks_text = "• Не выбраны"
            
            message = f"""
🚨 НОВЫЙ ЗАКАЗ #{booking_id}

👤 Клиент: {data.get('user_name', 'Гость')}
⏰ Время: {data.get('time', '')}
📍 Зона: {data.get('zone', '')}

💨 КАЛЬЯН:
• Вкус: {data.get('hookah', {}).get('flavor', '')}
• Крепость: {data.get('hookah', {}).get('strength', '')}/10

🍹 НАПИТКИ:
{drinks_text}

💰 Сумма: {data.get('totalPrice', 0)}₽
            """
            
            try:
                bot.send_message(chat_id=int(STAFF_CHAT_ID), text=message)
                print(f"✅ Уведомление отправлено в чат {STAFF_CHAT_ID}")
            except Exception as e:
                print(f"❌ Ошибка отправки: {e}")
        
        return jsonify({'status': 'success', 'booking_id': booking_id})
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': 'Bot is running!'})

@app.route('/test', methods=['GET'])
def test():
    return jsonify({
        'status': 'ok',
        'bot_configured': bot is not None,
        'chat_id': STAFF_CHAT_ID
    })

# === ЗАПУСК БОТА В ОТДЕЛЬНОМ ПОТОКЕ ===
def run_bot():
    """Запускает бота в режиме polling"""
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    
    print("🤖 Бот запущен в режиме polling...")
    application.run_polling(allowed_updates=["message"])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    
    # Запускаем бота в отдельном потоке
    if BOT_TOKEN:
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        print("🤖 Бот запущен в фоновом режиме")
    
    # Запускаем Flask сервер
    print(f"🚀 Flask сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
