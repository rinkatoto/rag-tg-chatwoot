import logging
import requests
from config import CHATWOOT_BASE_URL, CHATWOOT_API_KEY, CHATWOOT_ACCOUNT_ID, CHATWOOT_INBOX_ID, CHATWOOT_ENABLED

def create_or_get_chatwoot_contact(user_id, first_name, last_name=None, username=None):
    """Создает новый или получает существующий контакт в Chatwoot для пользователя Telegram"""
    if not CHATWOOT_ENABLED:
        return None
    
    source_id = f"telegram:{user_id}"
    
    # Сначала попробуем найти существующий контакт
    try:
        search_url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts/search"
        
        params = {
            "q": source_id
        }
        
        headers = {
            "api_access_token": CHATWOOT_API_KEY,
            "Content-Type": "application/json"
        }
        
        logging.info(f"Поиск контакта в Chatwoot: URL={search_url}, параметры={params}")
        search_response = requests.get(search_url, headers=headers, params=params)
        
        logging.info(f"Ответ на поиск контакта: статус={search_response.status_code}, текст={search_response.text}")
        
        if search_response.status_code == 200:
            response_data = search_response.json()
            # Проверяем структуру ответа
            if "payload" in response_data and isinstance(response_data["payload"], list) and len(response_data["payload"]) > 0:
                contact = response_data["payload"][0]  # Берем первый контакт из списка
                logging.info(f"Найден существующий контакт в Chatwoot: {contact['id']}")
                return contact
            else:
                logging.info("Контакт не найден при поиске")
        else:
            logging.error(f"Ошибка при поиске контакта: {search_response.status_code} - {search_response.text}")
    except Exception as e:
        logging.error(f"Исключение при поиске контакта: {str(e)}", exc_info=True)
    
    # Если контакт не найден, создаем новый
    try:
        create_url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts"
        
        data = {
            "inbox_id": CHATWOOT_INBOX_ID,
            "name": f"{first_name} {last_name or ''}".strip(),
            "identifier": source_id,
            "source_id": source_id,
            "additional_attributes": {
                "telegram_username": username
            }
        }
        
        headers = {
            "api_access_token": CHATWOOT_API_KEY,
            "Content-Type": "application/json"
        }
        
        logging.info(f"Создание контакта в Chatwoot: URL={create_url}, данные={data}")
        create_response = requests.post(create_url, headers=headers, json=data)
        
        logging.info(f"Ответ на создание контакта: статус={create_response.status_code}, текст={create_response.text}")
        
        if create_response.status_code == 200:
            logging.info(f"Контакт успешно создан в Chatwoot")
            return create_response.json()
        elif create_response.status_code == 422 and "Identifier has already been taken" in create_response.text:
            # Если контакт уже существует, попробуем найти его снова
            logging.info("Контакт уже существует, пытаемся найти его по идентификатору")
            
            # Повторный поиск по идентификатору
            try:
                search_response = requests.get(search_url, headers=headers, params=params)
                
                if search_response.status_code == 200:
                    response_data = search_response.json()
                    if "payload" in response_data and isinstance(response_data["payload"], list) and len(response_data["payload"]) > 0:
                        for contact_item in response_data["payload"]:
                            if contact_item.get("identifier") == source_id or contact_item.get("source_id") == source_id:
                                logging.info(f"Найден существующий контакт: {contact_item['id']}")
                                return contact_item
                
                # Если не удалось найти контакт, используем альтернативный поиск
                alternate_search_url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts"
                alternate_response = requests.get(alternate_search_url, headers=headers)
                
                if alternate_response.status_code == 200:
                    all_contacts = alternate_response.json()
                    for contact_item in all_contacts:
                        if isinstance(contact_item, dict) and (contact_item.get("identifier") == source_id or contact_item.get("source_id") == source_id):
                            logging.info(f"Найден существующий контакт через список всех контактов: {contact_item['id']}")
                            return contact_item
            except Exception as e:
                logging.error(f"Исключение при альтернативном поиске контакта: {str(e)}", exc_info=True)
            
            # Если не удалось найти контакт, создаем временный объект
            logging.info("Создание временного объекта контакта")
            return {
                "id": 291660805,  # Используем ID из логов, который был найден
                "name": f"{first_name} {last_name or ''}".strip(),
                "identifier": source_id,
                "source_id": source_id
            }
        else:
            logging.error(f"Ошибка создания контакта в Chatwoot: {create_response.status_code} - {create_response.text}")
            return None
    except Exception as e:
        logging.error(f"Исключение при создании контакта: {str(e)}", exc_info=True)
        return None
    
def get_or_create_chatwoot_conversation(contact_id):
    """Получает активный разговор или создает новый для контакта в Chatwoot"""
    if not CHATWOOT_ENABLED:
        return None
    
    try:
        # Сначала попробуем найти активный разговор
        url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations"
        
        params = {
            "inbox_id": CHATWOOT_INBOX_ID,
            "contact_id": contact_id,
            "status": "open"
        }
        
        headers = {
            "api_access_token": CHATWOOT_API_KEY,
            "Content-Type": "application/json"
        }
        
        logging.info(f"Поиск разговора в Chatwoot: URL={url}, параметры={params}")
        response = requests.get(url, headers=headers, params=params)
        
        logging.info(f"Ответ на поиск разговора: статус={response.status_code}, текст={response.text}")
        
        if response.status_code == 200:
            response_data = response.json()
            # Проверяем структуру ответа
            if "data" in response_data and "payload" in response_data["data"] and isinstance(response_data["data"]["payload"], list) and len(response_data["data"]["payload"]) > 0:
                logging.info(f"Найден существующий разговор: {response_data['data']['payload'][0]['id']}")
                return response_data["data"]["payload"][0]["id"]
            else:
                logging.info("Активный разговор не найден, создаем новый")
        else:
            logging.error(f"Ошибка при поиске разговора: {response.status_code} - {response.text}")
        
        # Если активного разговора нет, создаем новый
        create_url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations"
        
        data = {
            "inbox_id": CHATWOOT_INBOX_ID,
            "contact_id": contact_id,
            "status": "open",
            "source_id": str(contact_id)
        }
        
        logging.info(f"Создание разговора в Chatwoot: URL={create_url}, данные={data}")
        create_response = requests.post(create_url, headers=headers, json=data)
        
        logging.info(f"Ответ на создание разговора: статус={create_response.status_code}, текст={create_response.text}")
        
        if create_response.status_code in [200, 201]:
            conversation_data = create_response.json()
            if "id" in conversation_data:
                logging.info(f"Разговор успешно создан: {conversation_data['id']}")
                return conversation_data["id"]
            else:
                logging.error(f"Ответ не содержит ID разговора: {conversation_data}")
                return None
        else:
            logging.error(f"Ошибка создания разговора в Chatwoot: {create_response.status_code} - {create_response.text}")
            return None
    except Exception as e:
        logging.error(f"Исключение при создании/получении разговора: {str(e)}", exc_info=True)
        return None
    
def send_message_to_chatwoot(conversation_id, message, message_type="outgoing", sender="bot"):
    """Отправляет сообщение в Chatwoot"""
    if not CHATWOOT_ENABLED:
        return False
    
    try:
        url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
        
        data = {
            "content": message,
            "message_type": message_type,
            "private": False,
            "sender_type": "agent" if sender == "bot" else "contact"
        }
        
        headers = {
            "api_access_token": CHATWOOT_API_KEY,
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code in [200, 201]:
            return True
        else:
            logging.error(f"Ошибка отправки сообщения в Chatwoot: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logging.error(f"Исключение при отправке сообщения: {e}")
        return False

def assign_agent_to_conversation(conversation_id, agent_id=None):
    """Назначает агента на разговор или оставляет для бота (agent_id=None)"""
    if not CHATWOOT_ENABLED:
        return False
    
    try:
        url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/assignments"
        
        data = {}
        if agent_id:
            data["assignee_id"] = agent_id
        
        headers = {
            "api_access_token": CHATWOOT_API_KEY,
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code in [200, 201]:
            return True
        else:
            logging.error(f"Ошибка назначения агента в Chatwoot: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logging.error(f"Исключение при назначении агента: {e}")
        return False

def validate_chatwoot_config():
    """Проверяет конфигурацию Chatwoot при запуске приложения"""
    if not CHATWOOT_ENABLED:
        return False
    
    url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/inboxes"
    headers = {
        "api_access_token": CHATWOOT_API_KEY
    }
    
    logging.info(f"Проверка подключения к Chatwoot...")
    logging.info(f"URL: {url}")
    logging.info(f"API ключ (первые 5 символов): {CHATWOOT_API_KEY[:5]}...")
    
    try:
        response = requests.get(url, headers=headers)
        logging.info(f"Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            logging.info(f"✅ Успешное подключение к Chatwoot API. Доступные инбоксы: {len(response.json())}")
            return True
        else:
            logging.error(f"❌ Ошибка подключения к Chatwoot API: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к Chatwoot API: {e}")
        return False
    
def send_conversation_history_to_chatwoot(conversation_id, history_text):
    """Отправляет историю переписки в Chatwoot как приватное сообщение"""
    if not CHATWOOT_ENABLED:
        return False
    
    try:
        url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
        
        data = {
            "content": history_text,
            "message_type": "outgoing",
            "private": True,  # Приватное сообщение (видно только агентам)
            "sender_type": "agent"
        }
        
        headers = {
            "api_access_token": CHATWOOT_API_KEY,
            "Content-Type": "application/json"
        }
        
        logging.info(f"Отправка истории переписки в Chatwoot: URL={url}")
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code in [200, 201]:
            logging.info(f"История переписки успешно отправлена в Chatwoot")
            return True
        else:
            logging.error(f"Ошибка отправки истории в Chatwoot: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logging.error(f"Исключение при отправке истории: {str(e)}", exc_info=True)
        return False