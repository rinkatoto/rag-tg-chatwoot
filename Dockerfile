FROM python:3.10

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && \
apt-get install -y unzip curl && \
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && \
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | tee /etc/apt/sources.list.d/ngrok.list && \
apt-get update && \
apt-get install -y ngrok

# Создание необходимых директорий
RUN mkdir -p /app/data

# Контейнер просто запускается и ждёт команд
CMD ["sleep", "infinity"]
