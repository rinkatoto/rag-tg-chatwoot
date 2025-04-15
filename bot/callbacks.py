import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services.utils import user_states
from services.chatwoot_service import (
    create_or_get_chatwoot_contact, 
    get_or_create_chatwoot_conversation, 
    send_message_to_chatwoot, 
    assign_agent_to_conversation
)
from config import CHATWOOT_ENABLED

# Модифицируем обработчик кнопки соединения с оператором

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not CHATWOOT_ENABLED:
        await query.edit_message_text(
            text="К сожалению, соединение с оператором временно недоступно. Пожалуйста, попробуйте позже."
        )
        return
    
    if query.data == "connect_agent":
        try:
            # Проверяем, есть ли пользователь в системе
            if user_id not in user_states:
                # Если нет - создаем контакт и разговор
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
                            "with_agent": True,
                            "conversation_id": conversation_id,
                            "contact_id": contact["id"],
                            "history_sent": False
                        }
            else:
                # Если уже есть - просто обновляем статус
                user_states[user_id]["with_agent"] = True
            
            if user_id in user_states and "conversation_id" in user_states[user_id]:
                conversation_id = user_states[user_id]["conversation_id"]
                
                # Отправляем историю переписки в Chatwoot, если еще не отправляли
                if not user_states[user_id].get("history_sent", False):
                    history_text = get_formatted_history(user_id)
                    send_conversation_history_to_chatwoot(conversation_id, history_text)
                    user_states[user_id]["history_sent"] = True
                
                # Отправляем уведомление в Chatwoot, что пользователь запросил оператора
                send_message_to_chatwoot(
                    conversation_id, 
                    "Пользователь запросил соединение с оператором", 
                    "outgoing", 
                    "bot"
                )
                
                # Убираем назначение с бота, чтобы система могла назначить агента
                assign_agent_to_conversation(conversation_id, None)
                
                await query.edit_message_text(
                    text="Запрос на соединение с оператором отправлен. Пожалуйста, подождите, "
                         "скоро с вами свяжется наш специалист."
                )
            else:
                await query.edit_message_text(
                    text="Не удалось установить соединение с оператором. Пожалуйста, попробуйте позже."
                )
        except Exception as e:
            logging.error(f"Ошибка при соединении с оператором: {e}")
            await query.edit_message_text(
                text="Произошла ошибка при попытке соединения с оператором. Пожалуйста, попробуйте позже."
            )
    
    elif query.data == "back_to_bot":
        try:
            # Возвращаем пользователя к боту
            if user_id in user_states:
                user_states[user_id]["with_agent"] = False
                if "conversation_id" in user_states[user_id]:
                    conversation_id = user_states[user_id]["conversation_id"]
                    
                    # Отправляем уведомление в Chatwoot
                    send_message_to_chatwoot(
                        conversation_id, 
                        "Пользователь вернулся к общению с ботом", 
                        "outgoing", 
                        "bot"
                    )
                    
                    # Назначаем разговор назад на бота
                    assign_agent_to_conversation(conversation_id)
            
            keyboard = [
                [InlineKeyboardButton("Связаться с оператором", callback_data="connect_agent")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text="Вы вернулись к общению с ботом. Задайте свой вопрос.",
                reply_markup=reply_markup
            )
        except Exception as e:
            logging.error(f"Ошибка при возврате к боту: {e}")
            await query.edit_message_text(
                text="Произошла ошибка, но вы можете продолжить общение с ботом. Задайте свой вопрос."
            )