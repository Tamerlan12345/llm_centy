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
    # Файл: Centy_Llama_1.2B_Q4.gguf
    file_id = "16t8QU2Og28ArUk9WAccwb0xxf0y43GCi"
    output = "Centy_Llama_1.2B_Q4.gguf"
    
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
