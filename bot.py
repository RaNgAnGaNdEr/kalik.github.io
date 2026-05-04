import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters

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

# === API ДЛЯ MINI APP ===
@app.route('/booking', methods=['POST'])
def create_booking():
    try:
        data = request.json
        print(f"📦 Получен заказ: {data}")
        
        # Сохраняем в базу
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
🚨 <b>НОВЫЙ ЗАКАЗ #{booking_id}</b> 🚨

👤 <b>Клиент:</b> {data.get('user_name', 'Гость')}
⏰ <b>Время:</b> {data.get('time', '')}
📍 <b>Зона:</b> {data.get('zone', '')}

💨 <b>КАЛЬЯН:</b>
• Вкус: {data.get('hookah', {}).get('flavor', '')}
• Крепость: {data.get('hookah', {}).get('strength', '')}/10

🍹 <b>НАПИТКИ:</b>
{drinks_text}

💰 <b>Сумма:</b> {data.get('totalPrice', 0)}₽

🕐 {datetime.now().strftime('%H:%M:%S')}
            """
            
            try:
                bot.send_message(chat_id=int(STAFF_CHAT_ID), text=message, parse_mode='HTML')
                print(f"✅ Уведомление отправлено в чат {STAFF_CHAT_ID}")
            except Exception as e:
                print(f"❌ Ошибка отправки: {e}")
        else:
            print("⚠️ Бот не настроен")
        
        return jsonify({'status': 'success', 'booking_id': booking_id})
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# === КОМАНДЫ ДЛЯ БОТА (через вебхук) ===
def start(update, context):
    update.message.reply_text("🤖 Бот для приёма заказов работает!\n\nКоманды:\n/status - последние заказы")

def status(update, context):
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()
    c.execute("SELECT id, user_name, time, total_price, status FROM bookings ORDER BY id DESC LIMIT 5")
    orders = c.fetchall()
    conn.close()
    
    if orders:
        msg = "📋 <b>Последние 5 заказов:</b>\n\n"
        for o in orders:
            msg += f"#{o[0]} | {o[1]} | {o[2]} | {o[3]}₽ | {o[4]}\n"
        update.message.reply_text(msg, parse_mode='HTML')
    else:
        update.message.reply_text("📭 Заказов пока нет")

# === ВЕБХУК ===
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Получаем обновление от Telegram
        update = Update.de_json(request.get_json(force=True), bot)
        
        # Создаём диспетчер
        dispatcher = Dispatcher(bot, None, use_context=True)
        
        # Регистрируем обработчики
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("status", status))
        
        # Обрабатываем обновление
        dispatcher.process_update(update)
        
        return 'OK', 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return 'Error', 500

@app.route('/', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': 'Bot is running!'})

@app.route('/test', methods=['GET'])
def test():
    return jsonify({
        'status': 'ok',
        'bot_configured': bot is not None,
        'chat_id': STAFF_CHAT_ID,
        'webhook_url': f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo" if BOT_TOKEN else None
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Запуск бота на порту {port}")
    print(f"📱 Webhook URL: https://твой-бот.onrender.com/webhook")
    app.run(host='0.0.0.0', port=port, debug=False)
