# --- Этап 1: Получение скомпилированного бинарника llama-server ---
FROM ghcr.io/ggml-org/llama.cpp:server AS llama-bin


# --- Этап 2: Финальный образ бэкенда и фронтенда ---
FROM python:3.11-slim

# Установка системных зависимостей, необходимых для работы C++ llama-server на CPU
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем бинарный файл сервера llama.cpp из первого этапа
COPY --from=llama-bin /app/llama-server /usr/bin/llama-server


# Настройка рабочей директории
WORKDIR /app

# Копируем список зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скачиваем файл модели GGUF с Google Диска
RUN pip install --no-cache-dir gdown && \
    gdown --id 1Iwt06GYj3YH9pFxQfE7LqYGYFIZrehsn -O Qwen2.5-0.5B-Instruct.Q4_K_M.gguf

# Копируем код бэкенда и фронтенда
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY start.sh .

# Делаем скрипт запуска исполняемым
RUN chmod +x start.sh

# Дефолтные переменные окружения для Railway
ENV PORT=8000
ENV DATABASE_URL=""
ENV LLAMA_SERVER_PATH=/usr/bin/llama-server
ENV MODEL_PATH=/app/Qwen2.5-0.5B-Instruct.Q4_K_M.gguf
ENV LLAMA_PORT=8088
ENV LLAMA_THREADS=2
ENV LLAMA_NO_MMAP=false
ENV USE_MOCK_LLM=false

# Открываем порт бэкенда
EXPOSE 8000

# Запуск через скрипт-оркестратор
CMD ["./start.sh"]
