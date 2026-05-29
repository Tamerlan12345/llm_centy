import os
import sys
import subprocess

def install_and_import(package):
    try:
        import gdown
    except ImportError:
        print(f"Installing {package}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            import gdown
        except Exception as e:
            print(f"Failed to install {package} via pip: {e}")
            sys.exit(1)
    return gdown

def main():
    # Идентификатор папки или файла на Google Диске
    # Файл: Qwen2.5-0.5B-Instruct.Q4_K_M.gguf
    file_id = "1Iwt06GYj3YH9pFxQfE7LqYGYFIZrehsn"
    output = "Qwen2.5-0.5B-Instruct.Q4_K_M.gguf"
    
    # Проверяем, существует ли файл уже
    if os.path.exists(output):
        print(f"Файл {output} уже существует локально в директории.")
        return

    print(f"Инициализация загрузки файла {output} (ID: {file_id}) с Google Диска...")
    gdown_module = install_and_import("gdown")
    
    try:
        gdown_module.download(id=file_id, output=output, quiet=False)
        print("Загрузка успешно завершена!")
    except Exception as e:
        print(f"Ошибка при скачивании файла: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
