import os
import json
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS  # Добавляем CORS поддержку

app = Flask(__name__)
CORS(app)  # Разрешаем запросы с любых доменов

# Настройки из переменных окружения Render
BOT_TOKEN = os.environ.get('BOT_TOKEN')
STAFF_CHAT_ID = os.environ.get('STAFF_CHAT_ID')

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
                  created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Функция отправки сообщения в Telegram
def send_telegram_message(chat_id, text):
    """Отправляет сообщение через Telegram Bot API"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return None

# API для приёма заказов из Mini App
@app.route('/booking', methods=['POST', 'OPTIONS'])
def create_booking():
    # Обрабатываем preflight запрос (OPTIONS)
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        print(f"📦 Получен заказ: {data}")
        
        # Сохраняем в базу
        conn = sqlite3.connect('bookings.db')
        c = conn.cursor()
        c.execute('''INSERT INTO bookings 
                     (user_id, user_name, time, zone, flavor, strength, drinks, total_price, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (data.get('user_id', 0), 
                   data.get('user_name', 'Гость'), 
                   data.get('time', ''),
                   data.get('zone', ''),
                   data.get('hookah', {}).get('flavor', ''),
                   data.get('hookah', {}).get('strength', 5),
                   json.dumps(data.get('drinks', [])),
                   data.get('totalPrice', 0),
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        booking_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Формируем сообщение для персонала
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
        """
        
        # Отправляем в Telegram
        if BOT_TOKEN and STAFF_CHAT_ID:
            result = send_telegram_message(STAFF_CHAT_ID, message)
            if result and result.get('ok'):
                print(f"✅ Сообщение отправлено в чат {STAFF_CHAT_ID}")
            else:
                print(f"❌ Ошибка отправки: {result}")
        else:
            print("⚠️ BOT_TOKEN или STAFF_CHAT_ID не заданы")
        
        # Добавляем CORS заголовки в ответ
        response = jsonify({'status': 'success', 'booking_id': booking_id})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        response = jsonify({'status': 'error', 'message': str(e)})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/send_test', methods=['GET'])
def send_test():
    """Тестовая отправка сообщения"""
    if BOT_TOKEN and STAFF_CHAT_ID:
        result = send_telegram_message(STAFF_CHAT_ID, "✅ Бот работает! Тестовое сообщение.")
        return jsonify({'status': 'ok', 'result': result})
    return jsonify({'status': 'error', 'message': 'BOT_TOKEN or STAFF_CHAT_ID not set'})

@app.route('/', methods=['GET'])
def health():
    response = jsonify({'status': 'ok', 'message': 'Bot is running!'})
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route('/test', methods=['GET'])
def test():
    response = jsonify({
        'status': 'ok',
        'bot_token_set': bool(BOT_TOKEN),
        'chat_id_set': bool(STAFF_CHAT_ID),
        'chat_id': STAFF_CHAT_ID
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Сервер запущен на порту {port}")
    print(f"📱 BOT_TOKEN: {'✅ установлен' if BOT_TOKEN else '❌ не установлен'}")
    print(f"📱 STAFF_CHAT_ID: {'✅ установлен' if STAFF_CHAT_ID else '❌ не установлен'}")
    app.run(host='0.0.0.0', port=port, debug=False)
