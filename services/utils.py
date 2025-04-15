import re
import unicodedata
from collections import deque
import logging
from datetime import datetime

# === Очистка текста ===
def clean_text(text):
    cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', ' ', text)
    cleaned = re.sub(r'[\ud800-\udfff]', '', cleaned)
    cleaned = unicodedata.normalize('NFKC', cleaned)
    return cleaned.encode('utf-8', 'ignore').decode('utf-8')

# === Словарь для хранения истории вопросов пользователей ===
user_question_history = {}

# === Словарь для хранения полной истории сообщений ===
user_message_history = {}  # user_id -> [{"role": "user/bot", "text": "...", "timestamp": datetime}]

# === Отслеживание состояния пользователей ===
user_states = {}  # user_id -> {'with_agent': True/False, 'conversation_id': chatwoot_conv_id}

# === Проверка контекстности запроса ===
def is_contextual_followup(user_id, new_q, reranker):
    if user_id not in user_question_history:
        user_question_history[user_id] = deque(maxlen=4)
        return False
    
    for prev_q in user_question_history[user_id]:
        score = reranker.predict([(new_q, prev_q)])[0]
        logging.info(f"Сравнение с историей пользователя {user_id}: '{prev_q}' — {score:.2f}")
        if score > 0.6:
            return True
    return False

# === Добавление сообщения в историю ===
def add_message_to_history(user_id, role, text):
    """
    Добавляет сообщение в историю пользователя
    :param user_id: ID пользователя
    :param role: 'user' или 'bot'
    :param text: текст сообщения
    """
    if user_id not in user_message_history:
        user_message_history[user_id] = []
    
    user_message_history[user_id].append({
        "role": role,
        "text": text,
        "timestamp": datetime.now()
    })

# === Получение истории сообщений в формате для передачи ===
def get_formatted_history(user_id, max_messages=20):
    """
    Возвращает отформатированную историю сообщений пользователя
    :param user_id: ID пользователя
    :param max_messages: максимальное количество последних сообщений
    :return: строка с историей сообщений
    """
    if user_id not in user_message_history or not user_message_history[user_id]:
        return "История сообщений отсутствует."
    
    history = user_message_history[user_id][-max_messages:]
    formatted_history = "=== ИСТОРИЯ ПЕРЕПИСКИ ===\n\n"
    
    for msg in history:
        time_str = msg["timestamp"].strftime("%d.%m.%Y %H:%M:%S")
        role_str = "Клиент" if msg["role"] == "user" else "Бот"
        formatted_history += f"[{time_str}] {role_str}: {msg['text']}\n\n"
    
    return formatted_history