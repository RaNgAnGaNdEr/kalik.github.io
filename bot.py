import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Bot
from telegram.constants import ParseMode

app = Flask(__name__)

# Настройки из переменных окружения (добавишь в Render)
BOT_TOKEN = os.environ.get('BOT_TOKEN')
STAFF_CHAT_ID = int(os.environ.get('STAFF_CHAT_ID', 0))

bot = Bot(token=BOT_TOKEN)

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

@app.route('/booking', methods=['POST'])
def create_booking():
    data = request.json
    
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()
    c.execute('''INSERT INTO bookings 
                 (user_id, user_name, time, zone, flavor, strength, drinks, total_price, status, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (data['user_id'], data['user_name'], data['time'], data['zone'],
               data['hookah']['flavor'], data['hookah']['strength'],
               json.dumps(data['drinks']), data['totalPrice'],
               'new', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    booking_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Отправляем в Telegram
    message = f"""
🚨 НОВЫЙ ЗАКАЗ #{booking_id}
👤 {data['user_name']}
⏰ {data['time']} | 📍 {data['zone']}
💨 {data['hookah']['flavor']} ({data['hookah']['strength']}/10)
💰 {data['totalPrice']}₽
    """
    
    bot.send_message(chat_id=STAFF_CHAT_ID, text=message)
    
    return jsonify({'status': 'success', 'booking_id': booking_id})

@app.route('/')
def health():
    return 'Bot is running!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
