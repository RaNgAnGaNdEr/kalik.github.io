import os
import json
import sqlite3
import requests
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Настройки из переменных окружения Render
BOT_TOKEN = os.environ.get('BOT_TOKEN')
STAFF_CHAT_ID = os.environ.get('STAFF_CHAT_ID')
MANAGER_USERNAME = os.environ.get('MANAGER_USERNAME', 'phuket_tickets_manager')

# Лимиты мест для каждой зоны
ZONE_CAPACITY = {
    'Основная зона': 4,
    'VIP комната': 1,
    'Терраса': 3
}

# База данных
def init_db():
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  user_name TEXT,
                  date TEXT,
                  time TEXT,
                  zone TEXT,
                  flavor TEXT,
                  strength INTEGER,
                  drinks TEXT,
                  total_price INTEGER,
                  comment TEXT,
                  status TEXT,
                  created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Функция отправки сообщения в Telegram
def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return None

# Функция получения ссылки на пользователя
def get_user_mention(user_id, user_name):
    return f'<a href="tg://user?id={user_id}">{user_name}</a>'

# Функция проверки доступности мест
def check_availability(date, time, zone, exclude_booking_id=None):
    """Проверяет, есть ли свободные места в выбранной зоне на указанное время"""
    conn = sqlite3.connect('bookings.db')
    c = conn.cursor()
    
    # Время начала и окончания брони (2 часа слота)
    time_start = datetime.strptime(time, '%H:%M')
    time_end = time_start + timedelta(hours=2)
    time_end_str = time_end.strftime('%H:%M')
    
    # Если время перевалило за 23:59, учитываем следующий день
    if time_end_str < time:
        query = '''SELECT COUNT(*) FROM bookings 
                   WHERE date = ? AND zone = ? AND status IN ('active', 'accepted')
                   AND (time >= ? OR time <= ?)'''
        params = (date, zone, time, time_end_str)
    else:
        query = '''SELECT COUNT(*) FROM bookings 
                   WHERE date = ? AND zone = ? AND status IN ('active', 'accepted')
                   AND time >= ? AND time < ?'''
        params = (date, zone, time, time_end_str)
    
    if exclude_booking_id:
        query += " AND id != ?"
        params += (exclude_booking_id,)
    
    c.execute(query, params)
    booked_count = c.fetchone()[0]
    conn.close()
    
    capacity = ZONE_CAPACITY.get(zone, 4)
    return capacity - booked_count

# Функция получения доступности всех зон
def get_all_availability(date, time):
    """Возвращает количество свободных мест во всех зонах"""
    result = {}
    for zone in ZONE_CAPACITY:
        free = check_availability(date, time, zone)
        result[zone] = {
            'free': free,
            'total': ZONE_CAPACITY[zone],
            'available': free > 0
        }
    return result

# Функция форматирования заказа для клиента
def format_order_for_client(data, booking_id):
    drinks_list = data.get('drinks', [])
    if drinks_list:
        drinks_text = "\n".join([f"• {d['name']} x{d.get('quantity', 1)} - {d['price'] * d.get('quantity', 1)}₽" for d in drinks_list])
    else:
        drinks_text = "• Не выбраны"
    
    comment = data.get('comment', '')
    comment_text = f"\n\n📝 <b>Ваше примечание:</b>\n{comment}" if comment else ""
    
    return f"""
✅ <b>ВАШ ЗАКАЗ ПРИНЯТ!</b> ✅

🎫 <b>Номер заказа:</b> #{booking_id}
📅 <b>Дата:</b> {data.get('date', '')}
⏰ <b>Время:</b> {data.get('time', '')}
📍 <b>Зона:</b> {data.get('zone', '')}

💨 <b>КАЛЬЯН:</b>
• Вкус: {data.get('hookah', {}).get('flavor', '')}
• Крепость: {data.get('hookah', {}).get('strength', '')}/10

🍹 <b>НАПИТКИ:</b>
{drinks_text}
{comment_text}

💰 <b>Итого к оплате:</b> {data.get('totalPrice', 0)}₽

─────────────────────
📌 <b>Для изменения или отмены заказа</b>
свяжитесь с администратором:
👉 <a href="https://t.me/{MANAGER_USERNAME}">@{MANAGER_USERNAME}</a>
─────────────────────
    """

# Функция форматирования заказа для персонала
def format_order_for_staff(data, booking_id):
    drinks_list = data.get('drinks', [])
    if drinks_list:
        drinks_text = "\n".join([f"• {d['name']} x{d.get('quantity', 1)} - {d['price'] * d.get('quantity', 1)}₽" for d in drinks_list])
    else:
        drinks_text = "• Не выбраны"
    
    comment = data.get('comment', '')
    comment_text = f"\n\n📝 <b>Примечание клиента:</b>\n{comment}" if comment else ""
    
    user_link = get_user_mention(data.get('user_id', 0), data.get('user_name', 'Гость'))
    
    reply_markup = {
        'inline_keyboard': [
            [{'text': '📞 Написать клиенту', 'url': f'tg://user?id={data.get("user_id", 0)}'}]
        ]
    }
    
    message = f"""
🚨 <b>НОВЫЙ ЗАКАЗ #{booking_id}</b> 🚨

👤 <b>Клиент:</b> {user_link}
📅 <b>Дата:</b> {data.get('date', '')}
⏰ <b>Время:</b> {data.get('time', '')}
📍 <b>Зона:</b> {data.get('zone', '')}

💨 <b>КАЛЬЯН:</b>
• Вкус: {data.get('hookah', {}).get('flavor', '')}
• Крепость: {data.get('hookah', {}).get('strength', '')}/10

🍹 <b>НАПИТКИ:</b>
{drinks_text}
{comment_text}

💰 <b>Итого:</b> {data.get('totalPrice', 0)}₽
🕐 <b>Создан:</b> {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
    """
    
    return message, reply_markup

# API для проверки доступности мест
@app.route('/availability', methods=['GET'])
def get_availability():
    date = request.args.get('date')
    time = request.args.get('time')
    
    if not date or not time:
        return jsonify({'status': 'error', 'message': 'Date and time required'}), 400
    
    availability = get_all_availability(date, time)
    return jsonify({'status': 'success', 'availability': availability})

# API для приёма заказов из Mini App
@app.route('/booking', methods=['POST', 'OPTIONS'])
def create_booking():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        print(f"📦 Получен заказ: {data}")
        
        # Проверяем доступность мест
        free_spots = check_availability(data.get('date'), data.get('time'), data.get('zone'))
        if free_spots <= 0:
            return jsonify({
                'status': 'error', 
                'message': f'Извините, в зоне "{data.get("zone")}" на это время нет свободных мест. Выберите другое время или зону.'
            }), 409
        
        # Сохраняем в базу
        conn = sqlite3.connect('bookings.db')
        c = conn.cursor()
        c.execute('''INSERT INTO bookings 
                     (user_id, user_name, date, time, zone, flavor, strength, drinks, total_price, comment, status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (data.get('user_id', 0), 
                   data.get('user_name', 'Гость'), 
                   data.get('date', ''),
                   data.get('time', ''),
                   data.get('zone', ''),
                   data.get('hookah', {}).get('flavor', ''),
                   data.get('hookah', {}).get('strength', 5),
                   json.dumps(data.get('drinks', []), ensure_ascii=False),
                   data.get('totalPrice', 0),
                   data.get('comment', ''),
                   'active',
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        booking_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Отправляем сообщение персоналу
        staff_message, reply_markup = format_order_for_staff(data, booking_id)
        if BOT_TOKEN and STAFF_CHAT_ID:
            send_telegram_message(STAFF_CHAT_ID, staff_message, reply_markup)
        
        # Отправляем копию заказа клиенту
        client_message = format_order_for_client(data, booking_id)
        if BOT_TOKEN and data.get('user_id') and data.get('user_id') != 0:
            send_telegram_message(data['user_id'], client_message)
        
        response = jsonify({'status': 'success', 'booking_id': booking_id})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        response = jsonify({'status': 'error', 'message': str(e)})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

# API для обновления заказа
@app.route('/update', methods=['POST', 'OPTIONS'])
def update_booking():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        print(f"✏️ Обновление заказа: {data}")
        
        # Проверяем доступность мест (исключая текущий заказ)
        free_spots = check_availability(data.get('date'), data.get('time'), data.get('zone'), data.get('booking_id'))
        if free_spots <= 0:
            return jsonify({
                'status': 'error',
                'message': f'Извините, в зоне "{data.get("zone")}" на это время уже нет свободных мест.'
            }), 409
        
        # Обновляем заказ в базе
        conn = sqlite3.connect('bookings.db')
        c = conn.cursor()
        c.execute('''UPDATE bookings 
                     SET date = ?, time = ?, zone = ?, flavor = ?, strength = ?, 
                         drinks = ?, total_price = ?, comment = ?
                     WHERE id = ? AND user_id = ?''',
                  (data.get('date', ''),
                   data.get('time', ''),
                   data.get('zone', ''),
                   data.get('hookah', {}).get('flavor', ''),
                   data.get('hookah', {}).get('strength', 5),
                   json.dumps(data.get('drinks', []), ensure_ascii=False),
                   data.get('totalPrice', 0),
                   data.get('comment', ''),
                   data.get('booking_id'),
                   data.get('user_id', 0)))
        conn.commit()
        conn.close()
        
        # Отправляем уведомление об обновлении
        if BOT_TOKEN and STAFF_CHAT_ID:
            update_message = f"🔄 <b>ЗАКАЗ #{data.get('booking_id')} БЫЛ ИЗМЕНЁН</b>\n\n👤 Клиент: {data.get('user_name')}\n📅 Новая дата: {data.get('date')}\n⏰ Новое время: {data.get('time')}"
            send_telegram_message(STAFF_CHAT_ID, update_message)
        
        return jsonify({'status': 'success', 'booking_id': data.get('booking_id')})
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# API для отмены заказа
@app.route('/cancel', methods=['POST', 'OPTIONS'])
def cancel_booking():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        booking_id = data.get('booking_id')
        
        conn = sqlite3.connect('bookings.db')
        c = conn.cursor()
        c.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ? AND user_id = ?", 
                  (booking_id, data.get('user_id', 0)))
        conn.commit()
        conn.close()
        
        if BOT_TOKEN and STAFF_CHAT_ID:
            cancel_message = f"❌ <b>ЗАКАЗ #{booking_id} БЫЛ ОТМЕНЁН</b>\n\n👤 Клиент отменил бронирование."
            send_telegram_message(STAFF_CHAT_ID, cancel_message)
        
        return jsonify({'status': 'success'})
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Функция проверки и завершения просроченных заказов
def check_and_complete_orders():
    while True:
        try:
            conn = sqlite3.connect('bookings.db')
            c = conn.cursor()
            
            now = datetime.now()
            current_time_str = now.strftime('%H:%M')
            current_date_str = now.strftime('%Y-%m-%d')
            
            c.execute('''SELECT id, user_id, user_name, date, time, zone, flavor, strength, drinks, total_price, comment 
                         FROM bookings 
                         WHERE status = 'active' AND date <= ? AND time <= ?''', 
                      (current_date_str, current_time_str))
            expired_orders = c.fetchall()
            
            for order in expired_orders:
                booking_id = order[0]
                c.execute("UPDATE bookings SET status = 'completed' WHERE id = ?", (booking_id,))
                conn.commit()
                
                drinks = json.loads(order[8]) if order[8] else []
                drinks_text = "\n".join([f"• {d['name']} x{d.get('quantity', 1)}" for d in drinks]) if drinks else "• Не выбраны"
                
                complete_message = f"✅ <b>ЗАКАЗ #{booking_id} ЗАВЕРШЁН</b>\n\n👤 {order[2]}\n📅 {order[3]} {order[4]}\n📍 {order[5]}\n💨 {order[6]} ({order[7]}/10)\n🍹 {drinks_text}\n💰 {order[9]}₽"
                
                if BOT_TOKEN and STAFF_CHAT_ID:
                    send_telegram_message(STAFF_CHAT_ID, complete_message)
            
            conn.close()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        time.sleep(60)

def start_background_checker():
    thread = threading.Thread(target=check_and_complete_orders, daemon=True)
    thread.start()
    print("🔄 Фоновый проверщик заказов запущен")

@app.route('/send_test', methods=['GET'])
def send_test():
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
        'manager_username': MANAGER_USERNAME,
        'zone_capacity': ZONE_CAPACITY
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    start_background_checker()
    print(f"🚀 Сервер запущен на порту {port}")
    print(f"📦 Лимиты мест: {ZONE_CAPACITY}")
    app.run(host='0.0.0.0', port=port, debug=False)
