import os
import logging

# === Логирование ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# === Конфигурация ===
CHROMA_HOST = os.getenv("CHROMA_HOST", '91.228.154.144')
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8077"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "yuzhane")
EMBED_MODEL_PATH = os.getenv("EMBED_MODEL_PATH", "/app/models/sbert_cache/intfloat_multilingual-e5-base")
HF_API_KEY = os.getenv("HF_API_KEY")
HF_ENDPOINT_URL = os.getenv("HF_ENDPOINT_URL")
RERANKER_PATH = os.getenv("RERANKER_PATH", "/app/models/reranker_cache/cross-encoder_ms-marco-MiniLM-L-6-v2")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Chatwoot Configuration
CHATWOOT_BASE_URL = os.getenv("CHATWOOT_BASE_URL")
CHATWOOT_API_KEY = os.getenv("CHATWOOT_API_KEY")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID")
CHATWOOT_INBOX_ID = os.getenv("CHATWOOT_INBOX_ID")

# Флаг для работы с Chatwoot - по умолчанию отключен, если не заданы все необходимые параметры
CHATWOOT_ENABLED = bool(CHATWOOT_BASE_URL and CHATWOOT_API_KEY and CHATWOOT_ACCOUNT_ID and CHATWOOT_INBOX_ID)

# Промпт для RAG
RAG_PROMPT_TEMPLATE = """
<|system|>
Ты — профессиональный консультант по жилому комплексу. Твоя задача — давать точные и полезные ответы, опираясь **исключительно** на предоставленный контекст.

### Правила ответа:
1. **Точность** — если в контексте есть прямая информация, отвечай кратко и по делу.
2. **Счёт** — если вопрос касается количества, ВНИМАТЕЛЬНО перечисли все элементы в контексте, соответствующие запросу, и укажи их точное количество. Будь предельно тщательным в подсчетах.
3. **Перефразирование** — если запрошена не дословная информация, перескажи суть своими словами, сохраняя смысл.
4. **Неуверенность** — если сомневаешься в ответе, начни с: *"Полагаю..."* или *"Судя по данным..."*.
5. **Отсутствие информации** — если ответа нет в контексте, честно скажи: *"У меня нет информации по этому вопросу. Уточните детали у менеджера."*
6. **Вежливость** — будь дружелюбным, но лаконичным.

При подсчете количества, перечисли все найденные элементы и укажи общее количество в начале или в конце ответа.

<|user|>
Контекст:
{context}

Вопрос клиента:
{question}

<|assistant|>
"""