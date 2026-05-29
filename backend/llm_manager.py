import os
import sys
import time
import subprocess
import logging
import httpx
import asyncio

logger = logging.getLogger("centy.llm_manager")

class LLMManager:
    def __init__(self):
        # Путь к бинарному файлу llama-server
        self.llama_bin = os.getenv("LLAMA_SERVER_PATH", "llama-server")
        # Путь к модели GGUF
        self.model_path = os.getenv("MODEL_PATH", "Centy_Llama_1.2B_Q4.gguf")
        # Внутренний порт, на котором будет крутиться llama-server
        self.port = int(os.getenv("LLAMA_PORT", "8088"))
        # Количество потоков CPU
        self.threads = os.getenv("LLAMA_THREADS", "2")
        # Размер контекста (из Modelfile)
        self.ctx_size = os.getenv("LLAMA_CTX_SIZE", "3072")
        # Флаг отключения mmap (экономит RAM при жестких лимитах)
        self.no_mmap = os.getenv("LLAMA_NO_MMAP", "false").lower() == "true"
        
        # Режим заглушки (mock) для тестирования на Windows без бинарников
        self.use_mock = os.getenv("USE_MOCK_LLM", "false").lower() == "true"
        
        self.process = None

    def get_api_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self):
        if self.use_mock:
            logger.info("LLM Manager: Запуск в режиме MOCK (заглушка). Бинарник llama-server запускаться не будет.")
            return

        # Проверим наличие модели
        if not os.path.exists(self.model_path):
            # Если модели нет в корне, проверим в родительской папке (на случай запуска из папки backend)
            parent_model = os.path.join("..", self.model_path)
            if os.path.exists(parent_model):
                self.model_path = parent_model
            else:
                logger.error(f"Файл модели не найден по пути: {self.model_path}. Будет использован режим MOCK.")
                self.use_mock = True
                return

        # Попробуем проверить наличие llama-server
        try:
            # На Windows проверим наличие .exe
            if sys.platform == "win32" and not self.llama_bin.endswith(".exe"):
                if os.path.exists(self.llama_bin + ".exe"):
                    self.llama_bin += ".exe"
                elif os.path.exists(os.path.join("..", self.llama_bin + ".exe")):
                    self.llama_bin = os.path.join("..", self.llama_bin + ".exe")
        except Exception:
            pass

        # Проверим, доступен ли бинарник в PATH или по прямому пути
        binary_exists = False
        if os.path.exists(self.llama_bin) or os.path.exists(os.path.join(os.getcwd(), self.llama_bin)):
            binary_exists = True
        else:
            # Ищем в PATH
            for path in os.environ.get("PATH", "").split(os.pathsep):
                exts = [".exe"] if sys.platform == "win32" else [""]
                for ext in exts:
                    if os.path.exists(os.path.join(path, self.llama_bin + ext)):
                        binary_exists = True
                        break
                if binary_exists:
                    break

        if not binary_exists:
            logger.warning(f"Бинарный файл llama-server '{self.llama_bin}' не найден. Переключение в режим MOCK.")
            self.use_mock = True
            return

        # Формируем команду запуска
        cmd = [
            self.llama_bin,
            "-m", self.model_path,
            "-c", self.ctx_size,
            "--port", str(self.port),
            "-t", self.threads,
            "--host", "127.0.0.1",
        ]
        
        if self.no_mmap:
            cmd.append("--no-mmap")

        logger.info(f"Запуск llama-server: {' '.join(cmd)}")
        
        try:
            # Запускаем процесс в фоновом режиме
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Ждем инициализации сервера и проверяем healthcheck
            is_healthy = await self._wait_for_health()
            if not is_healthy:
                logger.error("llama-server не прошел healthcheck после запуска.")
                # Выведем ошибки
                stderr_output = ""
                try:
                    # Пробуем неблокирующе прочитать stderr
                    stderr_output = self.process.stderr.read() if self.process.stderr else ""
                except Exception:
                    pass
                logger.error(f"Ошибки llama-server:\n{stderr_output}")
                raise RuntimeError("Не удалось запустить llama-server")
            
            logger.info("llama-server успешно запущен и готов к работе.")
        except Exception as e:
            logger.error(f"Ошибка при запуске llama-server: {e}")
            logger.warning("Переключение в режим MOCK для продолжения работы бэкенда.")
            self.use_mock = True

    async def _wait_for_health(self, timeout_sec: int = 45) -> bool:
        """Ожидание доступности HTTP-сервера llama-server"""
        url = f"{self.get_api_url()}/health"
        start_time = time.time()
        
        await asyncio.sleep(2)  # Дадим серверу 2 секунды на старт
        
        async with httpx.AsyncClient() as client:
            while time.time() - start_time < timeout_sec:
                # Проверим, не упал ли сам процесс
                if self.process and self.process.poll() is not None:
                    logger.error("Процесс llama-server завершился досрочно.")
                    return False
                    
                try:
                    response = await client.get(url, timeout=1.0)
                    if response.status_code == 200:
                        # Возвращает JSON {"status": "ok"} или аналогичный
                        data = response.json()
                        if data.get("status") in ("ok", "healthy") or "status" in data:
                            return True
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass
                await asyncio.sleep(1.0)
                
        return False

    async def stop(self):
        if self.process:
            logger.info("Остановка процесса llama-server...")
            self.process.terminate()
            try:
                # Ждем корректного завершения
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Процесс не завершился по terminate. Принудительное завершение...")
                self.process.kill()
            self.process = None
            logger.info("Процесс llama-server остановлен.")
