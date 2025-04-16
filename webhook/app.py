import logging
import json
import traceback
import requests
from flask import Flask, request, jsonify
from config import TELEGRAM_BOT_TOKEN, CHATWOOT_ENABLED

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("webhook.log"), logging.StreamHandler()]
)
logger = logging.getLogger("webhook")

# Инициализация Flask-приложения
app = Flask(__name__)

# Состояния пользователей импортируются из services.utils
from services.utils import user_states

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обрабатывает вебхуки от Chatwoot и отправляет сообщения в Telegram"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        logger.info("\n--- Webhook от Chatwoot ---")
        logger.info(json.dumps(data, indent=2))
        
        # Обработка изменения статуса разговора
        if data.get("event") == "conversation_status_changed":
            return handle_status_change(data)
        
        # Обработка сообщений
        if data.get("event") in ["message_created", "message.created"]:
            return handle_message(data)
        
        logger.info("Webhook не содержит известных событий для обработки")
        return jsonify({"status": "ignored"}), 200
        
    except Exception as e:
        logger.error(f"Ошибка в webhook: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 200

def extract_telegram_id_from_identifier(identifier):
    """Извлекает Telegram ID из строки формата 'telegram:ID'"""
    if identifier and isinstance(identifier, str) and identifier.startswith("telegram:"):
        return identifier.split(":", 1)[1]
    return None

def handle_status_change(data):
    """Обрабатывает изменение статуса разговора"""
    try:
        conversation_data = data.get('conversation', {})
        conversation_id = conversation_data.get('id')
        new_status = conversation_data.get('status')
        
        logger.info(f"Обработка изменения статуса разговора {conversation_id} на {new_status}")
        
        # Мы удаляем автоматический возврат к боту при закрытии разговора,
        # как было запрошено в задании
        if new_status == 'resolved':
            # Получаем Telegram ID из meta.sender.identifier
            telegram_id = None
            if "meta" in conversation_data and "sender" in conversation_data["meta"]:
                identifier = conversation_data["meta"]["sender"].get("identifier")
                telegram_id = extract_telegram_id_from_identifier(identifier)
            
            if telegram_id:
                logger.info(f"Найден Telegram ID {telegram_id} для разговора {conversation_id}")
                
                # ИЗМЕНЕНИЕ: Не меняем статус with_agent на False автоматически
                # Пользователь остается с оператором даже после закрытия разговора
                
                # Отправляем сообщение в Telegram о завершении разговора
                send_telegram_message(
                    telegram_id, 
                    "Оператор завершил разговор."
                )
                
                return jsonify({"status": "conversation closed"}), 200
            else:
                logger.warning(f"Не найден Telegram ID для разговора {conversation_id}")
                
        return jsonify({"status": "processed"}), 200
    except Exception as e:
        logger.error(f"Ошибка при обработке изменения статуса: {e}", exc_info=True)
        return jsonify({"status": "error"}), 200

def handle_message(data):
    """Обрабатывает сообщения от оператора"""
    try:
        # Проверяем тип сообщения (от оператора к пользователю)
        message_type = data.get("message_type")
        sender_type = data.get("sender", {}).get("type")
        
        # Проверяем вложенную структуру
        if "message" in data:
            message_data = data.get("message", {})
            if not message_type:
                message_type = message_data.get("message_type")
            if not sender_type:
                sender_type = message_data.get("sender_type")
        
        content = data.get("content")
        if "message" in data and not content:
            content = data.get("message", {}).get("content")
        
        conversation_id = data.get("conversation", {}).get("id")
        
        logger.info(f"Анализ сообщения: type={message_type}, sender={sender_type}, conversation_id={conversation_id}")
        
        # NEW: Проверяем, является ли сообщение приватным через флаг private или атрибут private
        is_private = False
        
        if "message" in data and "private" in data["message"]:
            is_private = data["message"]["private"]
        elif "private" in data:
            is_private = data["private"]
            
        if is_private:
            logger.info(f"Игнорирование приватного сообщения")
            return jsonify({"status": "ignored_private_message"}), 200
        
        # ENHANCED: Проверяем наличие любых маркеров для внутренних сообщений
        if content:
            # Проверка на специальные префиксы
            internal_prefixes = ["[BOT_MESSAGE]", "[INTERNAL_MESSAGE]"]
            if any(content.startswith(prefix) for prefix in internal_prefixes):
                logger.info(f"Игнорирование внутреннего сообщения с префиксом")
                return jsonify({"status": "ignored_internal_message"}), 200
                
            # Проверка на содержимое, которое не нужно пересылать пользователю
            if "история переписки" in content.lower() or "=== история переписки ===" in content.lower():
                logger.info(f"Игнорирование сообщения с историей переписки")
                return jsonify({"status": "ignored_history_message"}), 200
                
            if "пользователь запросил соединение с оператором" in content.lower():
                logger.info(f"Игнорирование служебного сообщения о запросе оператора")
                return jsonify({"status": "ignored_service_message"}), 200
        
        # Проверяем, является ли это сообщением оператора пользователю
        if str(message_type).lower() != "outgoing" or (sender_type and sender_type.lower() != "agent" and sender_type.lower() != "user"):
            logger.info(f"Пропущено: не исходящее сообщение от оператора")
            return jsonify({"status": "ignored"}), 200
        
        if not conversation_id or not content:
            logger.warning("Нет conversation_id или content")
            return jsonify({"status": "missing_data"}), 200
        
        # Получаем Telegram ID из meta.sender.identifier
        telegram_chat_id = None
        if "conversation" in data and "meta" in data["conversation"] and "sender" in data["conversation"]["meta"]:
            identifier = data["conversation"]["meta"]["sender"].get("identifier")
            telegram_chat_id = extract_telegram_id_from_identifier(identifier)
            
            if telegram_chat_id:
                logger.info(f"Найден Telegram ID из meta.sender.identifier: {telegram_chat_id}")
        
        # Если не нашли ID, логируем ошибку
        if not telegram_chat_id:
            logger.warning(f"Не найден Telegram ID в meta.sender.identifier для conversation {conversation_id}")
            
            # Пытаемся найти хотя бы в user_states как запасной вариант
            for user_id, state in user_states.items():
                if str(state.get("conversation_id")) == str(conversation_id):
                    telegram_chat_id = str(user_id)
                    logger.info(f"Найден Telegram ID в user_states: {telegram_chat_id}")
                    break
            
            if not telegram_chat_id:
                logger.error("Не удалось найти Telegram ID для отправки сообщения")
                return jsonify({"status": "no_telegram_id"}), 200
        
        # Отправляем сообщение
        logger.info(f"Отправка сообщения в Telegram для пользователя {telegram_chat_id}")
        success = send_telegram_message(telegram_chat_id, content)
        
        if success:
            logger.info(f"Сообщение успешно отправлено в Telegram")
            return jsonify({"status": "sent_to_telegram"}), 200
        else:
            logger.error(f"Ошибка отправки сообщения в Telegram")
            return jsonify({"status": "telegram_error"}), 200
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 200

def send_telegram_message(chat_id, message):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": f"Оператор: {message}",
            "parse_mode": "HTML"
        }
        
        logger.info(f"Отправка в Telegram API: chat_id={chat_id}, текст={message[:50]}...")
        response = requests.post(url, json=data)
        response_data = response.json()
        
        if response.status_code == 200 and response_data.get("ok"):
            logger.info("Сообщение успешно отправлено в Telegram")
            return True
        else:
            logger.error(f"Telegram API ответил с ошибкой: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка Telegram: {str(e)}", exc_info=True)
        return False

@app.route('/webhook/test', methods=['GET'])
def test():
    return "Webhook server is running!", 200

def run_webhook_server():
    """Запускает Flask-сервер для обработки вебхуков"""
    logger.info("=" * 80)
    logger.info("Запуск Flask-сервера для вебхуков на порту 5011")
    logger.info(f"Chatwoot интеграция {'ВКЛЮЧЕНА' if CHATWOOT_ENABLED else 'ОТКЛЮЧЕНА'}")
    logger.info(f"Telegram токен {'настроен' if TELEGRAM_BOT_TOKEN else 'НЕ настроен'}")
    logger.info("=" * 80)
    app.run(host='0.0.0.0', port=5011, debug=False)