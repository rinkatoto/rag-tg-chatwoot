import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services.utils import (
    user_states, 
    add_message_to_history,  
    get_formatted_history    
)
from services.chatwoot_service import (
    create_or_get_chatwoot_contact, 
    get_or_create_chatwoot_conversation, 
    send_message_to_chatwoot, 
    assign_agent_to_conversation,
    send_conversation_history_to_chatwoot
)
from services.rag_service import process_question
from config import CHATWOOT_ENABLED

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Регистрация пользователя в Chatwoot
    if CHATWOOT_ENABLED:
        try:
            contact = create_or_get_chatwoot_contact(user_id, user.first_name, user.last_name, user.username)
            
            if contact and "id" in contact:
                # Получение или создание разговора
                conversation_id = get_or_create_chatwoot_conversation(contact["id"])
                
                if conversation_id:
                    # Сохраняем информацию о разговоре
                    user_states[user_id] = {
                        "with_agent": False,
                        "conversation_id": conversation_id,
                        "contact_id": contact["id"],
                        "history_sent": False
                    }
                    
                    # Назначение на бота (снятие с агентов)
                    assign_agent_to_conversation(conversation_id)
                    
                    # Отправляем приветственное сообщение в Chatwoot
                    welcome_msg = f"Начат новый разговор с пользователем {user.first_name}"
                    send_message_to_chatwoot(conversation_id, welcome_msg, "outgoing", "bot")
        except Exception as e:
            logging.error(f"Ошибка при регистрации пользователя в Chatwoot: {e}")
    
    # Отправка приветственного сообщения пользователю
    welcome_message = (
        "Здравствуйте! Я консультант по жилому комплексу. "
        "Задайте мне вопрос, и я постараюсь на него ответить."
    )
    
    # Сохраняем приветственное сообщение в историю
    add_message_to_history(user_id, "bot", welcome_message)
    
    if CHATWOOT_ENABLED and user_id in user_states:
        keyboard = [
            [InlineKeyboardButton("Связаться с оператором", callback_data="connect_agent")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message + " Если понадобится помощь оператора, нажмите кнопку ниже.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(welcome_message)
        
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if CHATWOOT_ENABLED and update.effective_user.id in user_states:
        keyboard = [
            [InlineKeyboardButton("Связаться с оператором", callback_data="connect_agent")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Вы можете задать мне любой вопрос о жилом комплексе, и я отвечу на основе доступной мне информации. "
            "Если нужна помощь оператора, нажмите кнопку ниже.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Вы можете задать мне любой вопрос о жилом комплексе, и я отвечу на основе доступной мне информации."
        )

# Модифицируем обработчик сообщений для сохранения истории

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, base_retriever, reranker):
    user_id = update.effective_user.id
    question = update.message.text
    
    # Сохраняем сообщение пользователя в историю
    add_message_to_history(user_id, "user", question)
    
    # Проверяем, содержит ли сообщение запрос на соединение с оператором
    operator_keywords = ["оператор", "агент", "консультант", "человек", "поддержка", 
                         "помощь оператора", "живой оператор", "соединить с оператором"]
    
    if any(keyword.lower() in question.lower() for keyword in operator_keywords):
        # Пользователь запросил оператора через текст
        await connect_with_agent(update, context)
        return
    
    chatwoot_conversation_id = None
    
    # Если Chatwoot включен, пытаемся использовать его
    if CHATWOOT_ENABLED:
        try:
            # Проверяем, зарегистрирован ли пользователь
            if user_id not in user_states:
                # Если нет - регистрируем
                contact = create_or_get_chatwoot_contact(
                    user_id, 
                    update.effective_user.first_name, 
                    update.effective_user.last_name, 
                    update.effective_user.username
                )
                
                if contact and "id" in contact:
                    conversation_id = get_or_create_chatwoot_conversation(contact["id"])
                    if conversation_id:
                        user_states[user_id] = {
                            "with_agent": False,
                            "conversation_id": conversation_id,
                            "contact_id": contact["id"],
                            "history_sent": False
                        }
                        
                        # Назначение на бота
                        assign_agent_to_conversation(conversation_id)
            
            # Отправляем сообщение пользователя в Chatwoot
            if user_id in user_states and "conversation_id" in user_states[user_id]:
                chatwoot_conversation_id = user_states[user_id]["conversation_id"]
                send_message_to_chatwoot(chatwoot_conversation_id, question, "incoming", "user")
                
                # Если пользователь общается с агентом, не отвечаем ботом
                if user_states[user_id].get("with_agent", False):
                    return
        except Exception as e:
            logging.error(f"Ошибка при взаимодействии с Chatwoot: {e}")
    
    # Отправка уведомления "печатает..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # Обработка запроса ботом
    response = await process_question(user_id, question, base_retriever, reranker)
    
    # Сохраняем ответ бота в историю
    add_message_to_history(user_id, "bot", response)
    
    # Добавляем информацию о возможности вызова оператора
    response_with_hint = (
        f"{response}\n\n"
        "Если вам нужна помощь оператора, просто напишите 'оператор' или 'нужен оператор'."
    )
    
    # Отправляем ответ пользователю (без кнопки)
    await update.message.reply_text(response_with_hint)
    
    # Отправляем ответ бота в Chatwoot, но с меткой [BOT_MESSAGE], чтобы избежать дублирования
    if CHATWOOT_ENABLED and user_id in user_states and "conversation_id" in user_states[user_id]:
        send_message_to_chatwoot(
            user_states[user_id]["conversation_id"], 
            f"[BOT_MESSAGE]{response}", 
            "outgoing", 
            "bot"
        )

async def connect_with_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Функция для соединения пользователя с оператором"""
    user_id = update.effective_user.id
    
    if not CHATWOOT_ENABLED:
        await update.message.reply_text(
            "К сожалению, соединение с оператором временно недоступно. Пожалуйста, попробуйте позже."
        )
        return
    
    try:
        # Проверяем, есть ли пользователь в системе
        if user_id not in user_states:
            # Если нет - создаем контакт и разговор
            logging.info(f"Создание контакта для пользователя {user_id}")
            contact = create_or_get_chatwoot_contact(
                user_id, 
                update.effective_user.first_name, 
                update.effective_user.last_name, 
                update.effective_user.username
            )
            
            if contact and "id" in contact:
                logging.info(f"Получение/создание разговора для контакта {contact['id']}")
                conversation_id = get_or_create_chatwoot_conversation(contact["id"])
                if conversation_id:
                    user_states[user_id] = {
                        "with_agent": True,
                        "conversation_id": conversation_id,
                        "contact_id": contact["id"],
                        "history_sent": False
                    }
                    logging.info(f"Пользователь {user_id} зарегистрирован в системе с conversation_id={conversation_id}")
                else:
                    logging.error(f"Не удалось получить/создать разговор для контакта {contact['id']}")
                    # Создаем временный conversation_id для тестирования
                    temp_conversation_id = f"temp_{user_id}_{int(time.time())}"
                    logging.info(f"Создан временный conversation_id: {temp_conversation_id}")
                    user_states[user_id] = {
                        "with_agent": True,
                        "conversation_id": temp_conversation_id,
                        "contact_id": contact["id"],
                        "history_sent": False,
                        "is_temporary": True
                    }
            else:
                logging.error("Не удалось создать/получить контакт")
        else:
            # Если уже есть - просто обновляем статус
            user_states[user_id]["with_agent"] = True
            logging.info(f"Пользователь {user_id} уже зарегистрирован, обновлен статус with_agent=True")
        
        if user_id in user_states and "conversation_id" in user_states[user_id]:
            conversation_id = user_states[user_id]["conversation_id"]
            logging.info(f"Использование разговора {conversation_id} для пользователя {user_id}")
            
            # Проверяем, является ли разговор временным
            is_temporary = user_states[user_id].get("is_temporary", False)
            
            if not is_temporary:
                # Отправляем историю переписки в Chatwoot, если еще не отправляли
                if not user_states[user_id].get("history_sent", False):
                    history_text = get_formatted_history(user_id)
                    logging.info(f"Отправка истории переписки в Chatwoot для разговора {conversation_id}")
                    # Добавляем специальный префикс [INTERNAL_MESSAGE] к истории переписки
                    send_message_to_chatwoot(
                        conversation_id, 
                        f"[INTERNAL_MESSAGE]История переписки: {history_text}", 
                        "outgoing", 
                        "bot",
                        True  # также делаем приватным на всякий случай
                    )
                    user_states[user_id]["history_sent"] = True
                
                # Отправляем уведомление в Chatwoot с префиксом [INTERNAL_MESSAGE]
                logging.info(f"Отправка уведомления о запросе оператора в Chatwoot для разговора {conversation_id}")
                send_message_to_chatwoot(
                    conversation_id, 
                    f"[INTERNAL_MESSAGE]Пользователь запросил соединение с оператором", 
                    "outgoing", 
                    "bot",
                    True  # делаем сообщение приватным
                )
                
                # Убираем назначение с бота, чтобы система могла назначить агента
                logging.info(f"Снятие назначения с бота для разговора {conversation_id}")
                assign_agent_to_conversation(conversation_id, None)
            
            await update.message.reply_text(
                "Запрос на соединение с оператором отправлен. Пожалуйста, подождите, "
                "скоро с вами свяжется наш специалист."
            )
        else:
            logging.error(f"Отсутствует conversation_id для пользователя {user_id}")
            await update.message.reply_text(
                "Не удалось установить соединение с оператором. Пожалуйста, попробуйте позже."
            )
    except Exception as e:
        logging.error(f"Ошибка при соединении с оператором: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "Произошла ошибка при попытке соединения с оператором. Пожалуйста, попробуйте позже."
        )