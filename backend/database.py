import os
import uuid
from datetime import datetime
from typing import AsyncGenerator
from sqlalchemy import String, DateTime, ForeignKey, Integer, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Поддержка автоматической замены протокола для асинхронного PostgreSQL в SQLAlchemy
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Локальный фолбек на SQLite для удобства локального тестирования
    DATABASE_URL = "sqlite+aiosqlite:///./chats.db"
else:
    # Railway передает postgresql://, но для asyncpg нужен postgresql+asyncpg://
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Создание асинхронного движка БД
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    # Для SQLite отключаем проверку потоков
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

# Асинб-сессия
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), default="Новый чат")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())

    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")
    logs = relationship("GenerationLog", back_populates="chat", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[str] = mapped_column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(50))  # 'user', 'assistant', 'system'
    content: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())

    chat = relationship("Chat", back_populates="messages")

class GenerationLog(Base):
    __tablename__ = "generation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[str] = mapped_column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())

    chat = relationship("Chat", back_populates="logs")

# Инициализация таблиц
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Зависимость для получения сессии БД в FastAPI эндпоинтах
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
