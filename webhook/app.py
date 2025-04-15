import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from config import CHATWOOT_ENABLED, TELEGRAM_BOT_TOKEN
from services.utils import user_states

# === Инициализация Flask для вебхука ===
app = Flask(__name__)

# === Вебхук для Chatwoot ===
@app.route('/webhook', methods=['POST'])
def chatwoot_webhook():
    """Обрабатывает вебхуки от Chatwoot для передачи сообщений от агентов пользователям"""
    if not CHATWOOT_ENABLED:
        return jsonify({"status": "chatwoot_disabled"}), 200
    
    try:
        data = request.json
        
        # Проверка на тип события - нас интересуют только сообщения
        if 'event' not in data or data['event'] != 'message_created':
            return jsonify({"status": "ignored"}), 200
        
        # Проверка, что это сообщение от агента
        message_data = data.get('message', {})
        if message_data.get('message_type') != 'outgoing' or message_data.get('sender_type') != 'agent':
            return jsonify({"status": "not agent message"}), 200
        
        conversation_data = data.get('conversation', {})
        conversation_id = conversation_data.get('id')
        
        # Найти пользователя по conversation_id
        telegram_user_id = None
        for user_id, state in user_states.items():
            if state.get('conversation_id') == conversation_id:
                telegram_user_id = user_id
                break
        
        if telegram_user_id:
            # Получаем содержимое сообщения
            message_content = message_data.get('content', '')
            
            # Асинхронно отправляем сообщение пользователю Telegram
            async def send_message():
                bot = Bot(token=TELEGRAM_BOT_TOKEN)
                
                # Если это первое сообщение агента, добавляем кнопку возврата к боту
                is_first_agent_message = False
                if telegram_user_id in user_states and not user_states[telegram_user_id].get('agent_responded', False):
                    user_states[telegram_user_id]['agent_responded'] = True
                    is_first_agent_message = True
                
                if is_first_agent_message:
                    keyboard = [
                        [InlineKeyboardButton("Вернуться к боту", callback_data="back_to_bot")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=f"Оператор: {message_content}",
                        reply_markup=reply_markup
                    )
                else:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=f"Оператор: {message_content}"
                    )
            
            # Запускаем асинхронную отправку
            asyncio.run(send_message())
            
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "user not found"}), 404
    except Exception as e:
        logging.error(f"Ошибка в вебхуке Chatwoot: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def run_webhook_server():
    """Запускает Flask-сервер для обработки вебхуков"""
    app.run(host='0.0.0.0', port=5011, debug=False)