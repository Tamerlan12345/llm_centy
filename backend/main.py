import os
import json
import time
import uuid
import logging
import asyncio
import httpx
from typing import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, delete, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from .database import init_db, get_db, Chat, Message, GenerationLog, AsyncSessionLocal
from .llm_manager import LLMManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("centy.backend")

# Инициализация LLM менеджера
llm_manager = LLMManager()

# Системный промпт из Modelfile
SYSTEM_PROMPT = (
    "Ты — Centy (Центи), официальный ИИ-ассистент финансовой группы Сентрас в Казахстане. "
    "Твоя цель — отвечать на вопросы о холдинге Сентрас (включая компании Centras Insurance, "
    "Коммеск-Өмір, Centras Securities) четко, профессионально, лаконично и строго по фактам. "
    "Отвечай прямо на вопрос, структурируй текст списками и полностью избегай \"воды\", "
    "длинных приветствий и лишних рассуждений."
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализируем таблицы базы данных
    logger.info("Инициализация базы данных...")
    try:
        await init_db()
        logger.info("База данных успешно инициализирована.")
    except Exception as e:
        logger.error(f"Не удалось инициализировать БД: {e}. Приложение продолжит работу.")
        
    # Запускаем модель llama-server
    logger.info("Запуск менеджера модели LLM...")
    await llm_manager.start()
    
    yield
    
    # Очистка при выключении
    logger.info("Остановка менеджера модели LLM...")
    await llm_manager.stop()

app = FastAPI(
    title="Centy AI Chat API",
    description="API для чат-сервиса Centy на базе Qwen2.5-0.5B-Instruct GGUF",
    version="1.0.0",
    lifespan=lifespan
)

# Разрешаем CORS для локальной разработки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic схемы
class ChatCreate(BaseModel):
    title: str = "Новый чат"

class ChatOut(BaseModel):
    id: str
    title: str
    created_at: str

    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    content: str

class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True

# --- API Эндпоинты ---

@app.get("/api/health")
async def health_check():
    """Проверка здоровья бэкенда и состояния LLM"""
    status_llm = "mock" if llm_manager.use_mock else "running"
    if not llm_manager.use_mock and (not llm_manager.process or llm_manager.process.poll() is not None):
        status_llm = "stopped_or_failed"
    return {
        "status": "healthy",
        "llm_mode": status_llm,
        "model_path": llm_manager.model_path,
        "port": llm_manager.port
    }

@app.get("/api/chats", response_model=List[ChatOut])
async def get_chats(db: AsyncSession = Depends(get_db)):
    """Получить список всех чатов, сортированный по дате создания (сначала новые)"""
    result = await db.execute(select(Chat).order_by(desc(Chat.created_at)))
    chats = result.scalars().all()
    # Преобразуем дату в ISO формат для фронтенда
    return [
        ChatOut(
            id=c.id,
            title=c.title,
            created_at=c.created_at.isoformat()
        ) for c in chats
    ]

@app.post("/api/chats", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def create_chat(payload: ChatCreate, db: AsyncSession = Depends(get_db)):
    """Создать новый сеанс чата"""
    new_chat = Chat(title=payload.title)
    db.add(new_chat)
    await db.commit()
    await db.refresh(new_chat)
    return ChatOut(
        id=new_chat.id,
        title=new_chat.title,
        created_at=new_chat.created_at.isoformat()
    )

@app.delete("/api/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    """Удалить чат и все связанные с ним сообщения и логи"""
    # Проверим существование
    result = await db.execute(select(Chat).filter(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Чат не найден")
    
    await db.execute(delete(Chat).filter(Chat.id == chat_id))
    await db.commit()
    return None

@app.get("/api/chats/{chat_id}/messages", response_model=List[MessageOut])
async def get_chat_messages(chat_id: str, db: AsyncSession = Depends(get_db)):
    """Получить историю сообщений для конкретного чата"""
    # Проверим существование чата
    chat_result = await db.execute(select(Chat).filter(Chat.id == chat_id))
    if not chat_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Чат не найден")

    result = await db.execute(
        select(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat()
        ) for m in messages
    ]

# Реализация генератора для SSE-стриминга
async def stream_llm_response(
    request: Request,
    chat_id: str,
    user_msg_content: str,
    db_session_factory,
    history_messages: list
):
    start_time = time.time()
    accumulated_content = []
    
    # Подготавливаем сообщения для контекста модели
    # Начинаем с системного промпта
    llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Добавляем историю
    for msg in history_messages:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})
        
    # Добавляем текущее сообщение пользователя
    llm_messages.append({"role": "user", "content": user_msg_content})
    
    # Вычисляем количество токенов в промпте (оценочно: ~1 токен на 4 символа в русском языке)
    total_prompt_chars = sum(len(m["content"]) for m in llm_messages)
    estimated_prompt_tokens = int(total_prompt_chars / 3.5)

    if llm_manager.use_mock:
        # --- РЕЖИМ ЗАГЛУШКИ (MOCK) ---
        logger.info("Генерация ответа в MOCK режиме...")
        mock_answers = [
            "Здравствуйте! Я Centy, ИИ-ассистент группы Сентрас. Рад помочь вам.",
            "Финансовая группа Сентрас включает в себя следующие ведущие компании:\n"
            "- **Centras Insurance** (страхование физических и юридических лиц)\n"
            "- **Коммеск-Өмір** (страхование жизни и здоровья)\n"
            "- **Centras Securities** (инвестиции и брокерские услуги на KASE)\n"
            "Если у вас есть конкретные вопросы по этим направлениям, я с удовольствием отвечу.",
            "Компания Centras Insurance предоставляет услуги автострахования (ОГПО, КАСКО), страхования имущества и путешествий. "
            "Вы можете оформить полис онлайн на официальном сайте или обратиться в филиалы.",
            "Коммеск-Өмір — старейшая страховая компания Казахстана, специализирующаяся на накопительном страховании жизни, "
            "пенсионном аннуитете и добровольном медицинском страховании. Мы заботимся о вашем будущем.",
            "Я готов ответить на любой ваш вопрос о холдинге Сентрас. Наш приоритет — прозрачность, надежность и инновации в Казахстане."
        ]
        
        # Выбираем ответ на основе ключевых слов в запросе
        prompt_lower = user_msg_content.lower()
        if "страхов" in prompt_lower or "insurance" in prompt_lower:
            response_text = mock_answers[2]
        elif "жизн" in prompt_lower or "коммеск" in prompt_lower:
            response_text = mock_answers[3]
        elif "брокер" in prompt_lower or "securities" in prompt_lower or "акци" in prompt_lower:
            response_text = mock_answers[1]
        elif "компани" in prompt_lower or "холдинг" in prompt_lower or "групп" in prompt_lower:
            response_text = mock_answers[1]
        else:
            response_text = mock_answers[0] + "\n\n" + mock_answers[4]

        # Делим ответ на маленькие кусочки для симуляции стриминга
        chunk_size = 3
        for i in range(0, len(response_text), chunk_size):
            if await request.is_disconnected():
                logger.info("Пользователь отключился от стрима (MOCK). Прерываем генерацию.")
                return
            
            chunk = response_text[i:i+chunk_size]
            accumulated_content.append(chunk)
            yield f"data: {json.dumps({'content': chunk})}\n\n"
            await asyncio.sleep(0.02) # Имитация задержки генерации

    else:
        # --- НАСТОЯЩИЙ ЗАПУСК ЧЕРЕЗ LLAMA-SERVER ---
        client_timeout = httpx.Timeout(60.0, connect=5.0)
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            try:
                # Отправляем запрос на локальный llama-server в формате OpenAI
                async with client.stream(
                    "POST",
                    f"{llm_manager.get_api_url()}/v1/chat/completions",
                    json={
                        "model": "qwen",
                        "messages": llm_messages,
                        "stream": True,
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "repeat_penalty": 1.2
                    }
                ) as response:
                    
                    if response.status_code != 200:
                        err_text = await response.aread()
                        logger.error(f"llama-server вернул ошибку {response.status_code}: {err_text}")
                        yield f"data: {json.dumps({'error': 'Ошибка сервера генерации текста'})}\n\n"
                        return

                    async for line in response.iter_lines():
                        if await request.is_disconnected():
                            logger.info("Клиент отключился. Прерываем генерацию LLM.")
                            break
                        
                        if not line:
                            continue
                        
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            
                            try:
                                data_json = json.loads(data_str)
                                choices = data_json.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    chunk = delta.get("content", "")
                                    if chunk:
                                        accumulated_content.append(chunk)
                                        yield f"data: {json.dumps({'content': chunk})}\n\n"
                            except Exception as parse_err:
                                logger.warning(f"Ошибка парсинга строки стрима: {parse_err}. Строка: {line}")
            except Exception as conn_err:
                logger.error(f"Не удалось подключиться к llama-server: {conn_err}")
                yield f"data: {json.dumps({'error': 'Связь с сервером генерации потеряна'})}\n\n"
                return

    # Завершаем стрим сообщением об окончании
    yield "data: [DONE]\n\n"

    # Записываем сгенерированный ответ ассистента в базу данных
    full_response = "".join(accumulated_content)
    latency_ms = int((time.time() - start_time) * 1000)
    estimated_completion_tokens = int(len(full_response) / 3.5)
    
    # Сохраняем логи в БД в отдельной сессии
    async with db_session_factory() as db:
        try:
            # Сохраняем сообщение ассистента
            assistant_msg = Message(
                id=str(uuid.uuid4()),
                chat_id=chat_id,
                role="assistant",
                content=full_response
            )
            db.add(assistant_msg)
            
            # Сохраняем лог генерации
            gen_log = GenerationLog(
                id=str(uuid.uuid4()),
                chat_id=chat_id,
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=estimated_completion_tokens,
                latency_ms=latency_ms
            )
            db.add(gen_log)
            
            # Обновим название чата, если это было первое сообщение и название по умолчанию "Новый чат"
            # Для этого узнаем, сколько сообщений в чате
            msg_count_result = await db.execute(
                select(func.count(Message.id)).filter(Message.chat_id == chat_id)
            )
            msg_count = msg_count_result.scalar() or 0
            
            if msg_count <= 2: # Включает только что созданные user_msg и assistant_msg
                # Обновим имя чата на основе первых 5 слов сообщения пользователя
                words = user_msg_content.split()
                new_title = " ".join(words[:5])
                if len(words) > 5:
                    new_title += "..."
                
                chat_result = await db.execute(select(Chat).filter(Chat.id == chat_id))
                chat = chat_result.scalar_one_or_none()
                if chat and chat.title == "Новый чат":
                    chat.title = new_title
                    
            await db.commit()
            logger.info(f"Успешно сохранен ответ ассистента и логи генерации (время: {latency_ms}мс, токены: P{estimated_prompt_tokens}/C{estimated_completion_tokens})")
        except Exception as db_err:
            await db.rollback()
            logger.error(f"Ошибка сохранения ответа ассистента в БД: {db_err}")

@app.post("/api/chats/{chat_id}/messages")
async def send_message(
    chat_id: str,
    payload: MessageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Отправить сообщение пользователя и запустить генерацию ответа от LLM"""
    # 1. Проверим существование чата
    chat_result = await db.execute(select(Chat).filter(Chat.id == chat_id))
    if not chat_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Чат не найден")

    # 2. Получим историю сообщений перед вставкой нового (для передачи контекста модели)
    history_result = await db.execute(
        select(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
    )
    history_db = history_result.scalars().all()
    history_list = [{"role": m.role, "content": m.content} for m in history_db]

    # 3. Сохраняем сообщение пользователя в БД
    user_message = Message(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="user",
        content=payload.content
    )
    db.add(user_message)
    await db.commit()
    
    # 4. Возвращаем StreamingResponse с SSE-стримом
    return StreamingResponse(
        stream_llm_response(
            request=request,
            chat_id=chat_id,
            user_msg_content=payload.content,
            db_session_factory=AsyncSessionLocal,
            history_messages=history_list
        ),
        media_type="text/event-stream"
    )

# --- Раздача фронтенда ---

# Определяем пути
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

if os.path.exists(FRONTEND_DIR):
    logger.info(f"Подключение фронтенда из папки: {FRONTEND_DIR}")
    
    # Монтируем статические файлы для стилей и скриптов
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    
    # Раздаем главный index.html на корневой запрос
    @app.get("/")
    async def read_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
else:
    logger.warning(f"Папка фронтенда не найдена по пути: {FRONTEND_DIR}. Статические файлы раздаваться не будут.")
