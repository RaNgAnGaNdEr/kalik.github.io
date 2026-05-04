import os
import json
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

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
                  comment TEXT,
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

# Функция форматирования заказа для клиента
def format_order_for_client(data, booking_id):
    """Форматирует заказ для отправки клиенту"""
    drinks_list = data.get('drinks', [])
    if drinks_list:
        drinks_text = "\n".join([f"• {d['name']} x{d.get('quantity', 1)} - {d['price'] * d.get('quantity', 1)}₽" for d in drinks_list])
    else:
        drinks_text = "• Не выбраны"
    
    comment = data.get('comment', '')
    comment_text = f"\n\n📝 <b>Примечание:</b>\n{comment}" if comment else ""
    
    return f"""
✅ <b>ВАШ ЗАКАЗ ПРИНЯТ!</b> ✅

🎫 <b>Номер заказа:</b> #{booking_id}
⏰ <b>Время:</b> {data.get('time', '')}
📍 <b>Зона:</b> {data.get('zone', '')}

💨 <b>КАЛЬЯН:</b>
• Вкус: {data.get('hookah', {}).get('flavor', '')}
• Крепость: {data.get('hookah', {}).get('strength', '')}/10
• Цена: {data.get('hookah', {}).get('price', 1300)}₽

🍹 <b>НАПИТКИ:</b>
{drinks_text}
{comment_text}
💰 <b>Итого к оплате:</b> {data.get('totalPrice', 0)}₽

⏳ Статус: Ожидает подтверждения
Скоро с вами свяжется администратор для уточнения деталей.
    """

# Функция форматирования заказа для персонала
def format_order_for_staff(data, booking_id):
    """Форматирует заказ для отправки персоналу"""
    drinks_list = data.get('drinks', [])
    if drinks_list:
        drinks_text = "\n".join([f"• {d['name']} x{d.get('quantity', 1)} - {d['price'] * d.get('quantity', 1)}₽" for d in drinks_list])
    else:
        drinks_text = "• Не выбраны"
    
    comment = data.get('comment', '')
    comment_text = f"\n\n📝 <b>Примечание клиента:</b>\n{comment}" if comment else ""
    
    return f"""
🚨 <b>НОВЫЙ ЗАКАЗ #{booking_id}</b> 🚨

👤 <b>Клиент:</b> {data.get('user_name', 'Гость')}
🆔 <b>ID клиента:</b> <code>{data.get('user_id', 0)}</code>
⏰ <b>Время:</b> {data.get('time', '')}
📍 <b>Зона:</b> {data.get('zone', '')}

💨 <b>КАЛЬЯН:</b>
• Вкус: {data.get('hookah', {}).get('flavor', '')}
• Крепость: {data.get('hookah', {}).get('strength', '')}/10
• Цена: {data.get('hookah', {}).get('price', 1300)}₽

🍹 <b>НАПИТКИ:</b>
{drinks_text}
{comment_text}

💰 <b>Итого:</b> {data.get('totalPrice', 0)}₽
🕐 <b>Создан:</b> {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
    """

# API для приёма заказов из Mini App
@app.route('/booking', methods=['POST', 'OPTIONS'])
def create_booking():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        print(f"📦 Получен заказ: {data}")
        
        # Сохраняем в базу
        conn = sqlite3.connect('bookings.db')
        c = conn.cursor()
        c.execute('''INSERT INTO bookings 
                     (user_id, user_name, time, zone, flavor, strength, drinks, total_price, comment, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (data.get('user_id', 0), 
                   data.get('user_name', 'Гость'), 
                   data.get('time', ''),
                   data.get('zone', ''),
                   data.get('hookah', {}).get('flavor', ''),
                   data.get('hookah', {}).get('strength', 5),
                   json.dumps(data.get('drinks', []), ensure_ascii=False),
                   data.get('totalPrice', 0),
                   data.get('comment', ''),
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        booking_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Отправляем сообщение персоналу
        staff_message = format_order_for_staff(data, booking_id)
        if BOT_TOKEN and STAFF_CHAT_ID:
            result_staff = send_telegram_message(STAFF_CHAT_ID, staff_message)
            if result_staff and result_staff.get('ok'):
                print(f"✅ Сообщение персоналу отправлено в чат {STAFF_CHAT_ID}")
            else:
                print(f"❌ Ошибка отправки персоналу: {result_staff}")
        
        # Отправляем копию заказа клиенту (если есть user_id)
        client_message = format_order_for_client(data, booking_id)
        if BOT_TOKEN and data.get('user_id') and data.get('user_id') != 0:
            result_client = send_telegram_message(data['user_id'], client_message)
            if result_client and result_client.get('ok'):
                print(f"✅ Копия заказа отправлена клиенту {data['user_id']}")
            else:
                print(f"❌ Ошибка отправки клиенту: {result_client}")
        else:
            print("⚠️ Невозможно отправить копию клиенту: user_id не указан")
        
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

# Эндпоинт для обработки данных из tg.sendData()
@app.route('/webhook_data', methods=['POST'])
def handle_webhook_data():
    """Обрабатывает данные, отправленные через tg.sendData()"""
    try:
        data = request.json
        print(f"📨 Получены данные из tg.sendData(): {data}")
        
        action = data.get('action')
        
        if action == 'send_copy':
            # Отправляем копию заказа клиенту
            chat_id = data.get('chat_id')
            message = data.get('message')
            if chat_id and message:
                result = send_telegram_message(chat_id, message)
                return jsonify({'status': 'ok', 'result': result})
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"❌ Ошибка в webhook_data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
