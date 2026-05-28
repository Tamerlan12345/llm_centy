#!/bin/sh
# Скрипт запуска веб-приложения на Railway

echo "=== Запуск Centy AI Чат-сервиса ==="
echo "Используемый порт: ${PORT:-8000}"
echo "Путь к модели: ${MODEL_PATH}"
echo "Количество потоков CPU: ${LLAMA_THREADS:-2}"

# Запускаем FastAPI бэкенд через uvicorn в качестве основного процесса контейнера.
# Бэкенд на старте через lifespan автоматически запустит llama-server.
exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
