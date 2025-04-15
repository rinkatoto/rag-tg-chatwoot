import time
import logging
import requests
from langchain.prompts import PromptTemplate
from langchain_core.documents import Document

from config import HF_API_KEY, HF_ENDPOINT_URL, RAG_PROMPT_TEMPLATE
from services.utils import clean_text, user_question_history, is_contextual_followup
from collections import deque

# Инициализация промпта
custom_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=RAG_PROMPT_TEMPLATE
)

# === Запрос пользователя (RAG пайплайн) ===
async def process_question(user_id, question, base_retriever, reranker):
    logging.info(f"Запрос от пользователя {user_id}: {question}")
    try:
        start = time.time()

        clean_question = clean_text(question)

        # Инициализация истории вопросов пользователя, если нет
        if user_id not in user_question_history:
            user_question_history[user_id] = deque(maxlen=4)

        use_context = is_contextual_followup(user_id, clean_question, reranker)
        if not use_context:
            user_question_history[user_id].clear()
            logging.info(f"Контекст сброшен для пользователя {user_id}: тема изменилась")
        user_question_history[user_id].append(clean_question)

        docs = base_retriever.get_relevant_documents(clean_question)
        logging.info(f"Найдено документов: {len(docs)}")

        cleaned_docs = [Document(page_content=clean_text(doc.page_content), metadata=doc.metadata) for doc in docs]

        if cleaned_docs:
            rerank_inputs = [(clean_question, doc.page_content) for doc in cleaned_docs]
            scores = reranker.predict(rerank_inputs)
            reranked_docs = sorted(zip(cleaned_docs, scores), key=lambda x: x[1], reverse=True)
            cleaned_docs = [doc for doc, _ in reranked_docs]

        if not cleaned_docs:
            logging.warning("После очистки не осталось документов")
            return "Не удалось найти подходящую информацию для ответа на ваш вопрос."

        combined_context = "\n\n".join([doc.page_content for doc in cleaned_docs])
        
        try:
            prompt = custom_prompt.format(context=combined_context, question=clean_question)

            payload = {
                "prompt": prompt,
                "max_new_tokens": 320,
                "temperature": 0.3,
                "stop": ["</s>"]
            }

            headers = {
                "Authorization": f"Bearer {HF_API_KEY}",
                "Content-Type": "application/json"
            }

            response = requests.post(HF_ENDPOINT_URL, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                if isinstance(result, dict) and "content" in result:
                    response_text = result["content"]
                elif isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict) and "content" in result[0]:
                    response_text = result[0]["content"]
                else:
                    response_text = str(result)

                response_text = clean_text(response_text)
                logging.info(f"Ответ от модели: {response_text}")
                return response_text.strip()
            else:
                logging.error(f"Ошибка от API: {response.status_code} - {response.text}")
                return "Произошла ошибка при обработке вашего запроса через языковую модель."

        except Exception as e:
            logging.error(f"Ошибка при вызове LLM: {e}")
            return "Произошла ошибка при обработке вашего запроса через языковую модель."

        end = time.time()
        logging.info(f"Время выполнения: {end - start:.2f} секунд")

    except Exception as e:
        logging.error(f"Ошибка в процессе обработки: {e}")
        return "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте другой вопрос."