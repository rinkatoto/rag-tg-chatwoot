import threading
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder
from huggingface_hub import InferenceClient

from config import (
    CHROMA_HOST, 
    CHROMA_PORT, 
    COLLECTION_NAME, 
    EMBED_MODEL_PATH, 
    RERANKER_PATH, 
    HF_ENDPOINT_URL, 
    HF_API_KEY, 
    TELEGRAM_BOT_TOKEN, 
    CHATWOOT_ENABLED
)
from services.chatwoot_service import validate_chatwoot_config
from bot.handlers import start, help_command, handle_message
from bot.callbacks import button_callback
from webhook.app import run_webhook_server

def main():
    global CHATWOOT_ENABLED
    
    # Проверяем соединение с Chatwoot
    chatwoot_available = validate_chatwoot_config()
    if not chatwoot_available:
        logging.warning("⚠️ Интеграция с Chatwoot отключена из-за проблем с конфигурацией")
        CHATWOOT_ENABLED = False
    
    # === Инициализация моделей ===
    logging.info("Инициализация моделей и подключения к базе данных...")
    chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT, ssl=False)
    embedding_function = HuggingFaceEmbeddings(model_name=EMBED_MODEL_PATH, model_kwargs={"device": "cpu"})
    vectorstore = Chroma(client=chroma_client, collection_name=COLLECTION_NAME, embedding_function=embedding_function)
    base_retriever = vectorstore.as_retriever(search_kwargs={"k": 50})
    reranker = CrossEncoder(RERANKER_PATH)
    
    hf_client = InferenceClient(model=HF_ENDPOINT_URL, token=HF_API_KEY)
    
    # Создание и запуск Telegram бота
    logging.info("Настройка Telegram бота...")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчик колбеков от кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Обработчик текстовых сообщений
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            lambda update, context: handle_message(update, context, base_retriever, reranker)
        )
    )
    
    # Запуск Flask для вебхука в отдельном потоке, только если Chatwoot включен
    if CHATWOOT_ENABLED:
        logging.info("Запуск вебхука для Chatwoot...")
        threading.Thread(target=run_webhook_server).start()
    
    # Запуск бота
    logging.info(f"Запуск Telegram бота {'с' if CHATWOOT_ENABLED else 'без'} интеграции Chatwoot...")
    application.run_polling()

if __name__ == "__main__":
    main()