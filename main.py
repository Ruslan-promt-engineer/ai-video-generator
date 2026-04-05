# main.py — быстрый тест генерации через консоль
import sys
from video_service import video_service
import time

def main():
    if len(sys.argv) < 2:
        print("💡 Использование: python main.py 'твой промпт'")
        print("Пример: python main.py 'Космический корабль пролетает над облаками'")
        return

    prompt = " ".join(sys.argv[1:])
    print(f"🚀 Генерация: {prompt}\n")
    
    try:
        task_id = video_service.create_task(prompt)
        print(f"🆔 Task ID: {task_id}")
        print("⏳ Ожидание завершения (нажми Ctrl+C для отмены)...\n")

        while True:
            time.sleep(3)
            info = video_service.get_status(task_id)
            if not info: break
            
            status, progress = info["status"], info["progress"]
            print(f"\r[{status.upper()}] {progress:.1f}%  ", end="", flush=True)
            
            if status == "completed":
                print(f"\n✅ Готово! Файл: {info['file_path']}")
                break
            elif status in ("failed", "error"):
                print(f"\n❌ Ошибка: {info.get('error', 'Неизвестно')}")
                break
    except KeyboardInterrupt:
        print("\n⚠️ Отменено пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()

### Для запуска в терминале:
#python main.py "Космическая станция на орбите Земли, вид из иллюминатора, 4K"
