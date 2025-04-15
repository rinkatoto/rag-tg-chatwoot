# webhook_server.py
from flask import Flask, request, jsonify
import logging
import requests
import json
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("webhook.log"), logging.StreamHandler()]
)

app = Flask(__name__)

# Константы для Telegram и Chatwoot
TELEGRAM_BOT_TOKEN = "7743758924:AAGQmxD5Pw1zj83rD5ouned9rmVcuzsQ86k"
CHATWOOT_API_BASE_URL = os.getenv("CHATWOOT_BASE_URL", "https://app.chatwoot.com")
CHATWOOT_API_ACCESS_TOKEN = os.getenv("CHATWOOT_API_KEY", "YHsU1PGaCqcVXqg4wYDYYW79")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID", "117681")
CHATWOOT_INBOX_ID = os.getenv("CHATWOOT_INBOX_ID", "61964")

conversation_telegram_map = {}
MAPPING_FILE = "conversation_mapping.json"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True, silent=True) or {}
        logging.info("\n--- Webhook от Chatwoot ---")
        logging.info(json.dumps(data, indent=2))

        # Проверка одиночного сообщения
        if data.get("event") in ["message_created", "message.created"]:
            message_type = data.get("message_type")
            sender_type = data.get("sender", {}).get("type")
            content = data.get("content")
            conversation_id = str(data.get("conversation", {}).get("id"))

            if str(message_type).lower() != "outgoing" or str(sender_type).lower() != "user":
                logging.info(f"Пропущено: не outgoing (message_type={message_type}, sender_type={sender_type})")
                return jsonify({"status": "ignored"}), 200

            if not conversation_id or not content:
                logging.warning("Нет conversation_id или content")
                return jsonify({"status": "ignored"}), 200

            # Проверяем, есть ли идентификатор в данных напрямую
            telegram_chat_id = None
            if "meta" in data.get("conversation", {}) and "sender" in data["conversation"]["meta"]:
                identifier = data["conversation"]["meta"]["sender"].get("identifier")
                if identifier and identifier.startswith("telegram:"):
                    telegram_chat_id = identifier.split(":", 1)[1]
                    logging.info(f"Найден Telegram ID напрямую: {telegram_chat_id}")
            
            # Если не нашли напрямую, используем сохраненный маппинг
            if not telegram_chat_id:
                telegram_chat_id = get_telegram_chat_id(conversation_id)
            
            if not telegram_chat_id:
                logging.warning(f"Нет chat_id для conversation {conversation_id}")
                return jsonify({"status": "no_chat_id"}), 200

            success = send_telegram_message(telegram_chat_id, content)
            if success:
                logging.info(f"Отправлено в Telegram: {telegram_chat_id}")
            else:
                logging.error(f"Ошибка отправки в Telegram: {telegram_chat_id}")

            return jsonify({"status": "sent_to_telegram"}), 200

        logging.info("Webhook не содержит сообщений для обработки")
        return jsonify({"status": "ignored"}), 200

    except Exception as e:
        logging.error(f"Ошибка в webhook: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

def send_telegram_message(chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": f"Оператор: {message}",
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data)
        response_data = response.json()
        if not response.status_code == 200:
            logging.error(f"Telegram API ответил с ошибкой: {response_data}")
        return response.status_code == 200
    except Exception as e:
        logging.error(f"Ошибка Telegram: {str(e)}", exc_info=True)
        return False

def get_telegram_chat_id(conversation_id):
    # Сначала проверяем локальный кэш
    if conversation_id in conversation_telegram_map:
        return conversation_telegram_map[conversation_id]

    try:
        url = f"{CHATWOOT_API_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}"
        headers = {"api_access_token": CHATWOOT_API_ACCESS_TOKEN}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            chat_id = find_telegram_chat_id(data)
            if chat_id:
                save_conversation_mapping(conversation_id, chat_id)
                return chat_id
        logging.warning(f"Не найден Telegram ID в данных: {response.text}")
    except Exception as e:
        logging.error(f"Ошибка получения chat_id: {str(e)}", exc_info=True)
    return None

def find_telegram_chat_id(obj):
    """
    Рекурсивно ищет идентификатор Telegram в объекте данных
    """
    if not isinstance(obj, dict):
        return None

    # Приоритетный поиск по ключу identifier в формате 'telegram:<id>'
    if "meta" in obj and "sender" in obj["meta"]:
        identifier = obj["meta"]["sender"].get("identifier")
        if identifier and identifier.startswith("telegram:"):
            chat_id = identifier.split(":", 1)[1]
            logging.info(f"Найден Telegram ID через meta.sender.identifier: {chat_id}")
            return chat_id
    
    # Проверяем identifier напрямую
    identifier = obj.get("identifier")
    if identifier and identifier.startswith("telegram:"):
        chat_id = identifier.split(":", 1)[1]
        logging.info(f"Найден Telegram ID через identifier: {chat_id}")
        return chat_id
    
    # Проверяем другие возможные поля
    for key in ["telegram_chat_id", "chat_id", "source_id", "telegram_id"]:
        if key in obj and obj[key]:
            logging.info(f"Найден Telegram ID через ключ {key}: {obj[key]}")
            return obj[key]

    # Рекурсивный поиск по вложенным объектам
    for key, value in obj.items():
        if isinstance(value, dict):
            result = find_telegram_chat_id(value)
            if result:
                return result
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result = find_telegram_chat_id(item)
                    if result:
                        return result
    return None

def save_conversation_mapping(conversation_id, telegram_chat_id):
    conversation_telegram_map[conversation_id] = telegram_chat_id
    try:
        with open(MAPPING_FILE, 'w') as f:
            json.dump(conversation_telegram_map, f)
    except Exception as e:
        logging.error(f"Ошибка при сохранении маппинга: {str(e)}")

def load_conversation_mappings():
    global conversation_telegram_map
    try:
        if os.path.exists(MAPPING_FILE):
            with open(MAPPING_FILE, 'r') as f:
                conversation_telegram_map = json.load(f)
        else:
            conversation_telegram_map = {}
    except Exception as e:
        logging.error(f"Ошибка при загрузке маппинга: {str(e)}")

@app.route('/test', methods=['GET'])
def test():
    return "Webhook server is running!", 200

@app.route('/debug/mappings', methods=['GET'])
def debug_mappings():
    return jsonify(conversation_telegram_map)

if __name__ == '__main__':
    load_conversation_mappings()
    app.run(host='0.0.0.0', port=5000, debug=True)