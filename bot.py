import os
import time
import threading
import telebot
from telebot import types
from video_service import video_service
from dotenv import load_dotenv
import logging

# ─── Настройка логирования ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env файле! Добавьте строку BOT_TOKEN=ваш_токен")

bot = telebot.TeleBot(BOT_TOKEN)

# Хранилище активных задач пользователей: user_id -> {task_id, msg_id, status, prompt}
active_tasks = {}

# ─── Команды ───────────────────────────────────────────────────────────────
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = (
        "🎬 **Привет! Я AI-бот для генерации видео.**\n\n"
        "Просто отправь мне описание сцены, например:\n"
        "• _Кинематографичный закат над океаном_\n"
        "• _Кот в космосе в стиле Pixar_\n\n"
        "⏱️ Генерация занимает 1–3 минуты. Жди уведомление в чате!"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ─── Обработка текста (промптов) ───────────────────────────────────────────
@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    prompt = message.text.strip()

    # Проверка: не запущена ли уже задача у этого пользователя
    if user_id in active_tasks and active_tasks[user_id].get('status') in ['queued', 'in_progress', 'downloading']:
        bot.reply_to(message, "⏳ Подожди, предыдущее видео ещё генерируется!")
        return

    # Отправляем стартовое сообщение с прогресс-баром
    status_msg = bot.reply_to(message, "🚀 Запускаю генерацию...\n\n[░░░░░░░░░░░░░░░░░░░░] 0%")

    try:
        # 1. Создаём задачу через наше ядро
        task_id = video_service.create_task(prompt)
        
        # 2. Сохраняем состояние
        active_tasks[user_id] = {
            'task_id': task_id,
            'msg_id': status_msg.message_id,
            'status': 'queued',
            'prompt': prompt
        }

        # 3. Запускаем фоновый мониторинг
        thread = threading.Thread(target=monitor_progress, args=(user_id,), daemon=True)
        thread.start()

    except Exception as e:
        logging.error(f"Ошибка создания задачи: {e}")
        bot.edit_message_text(f"❌ Ошибка запуска: {e}", chat_id=user_id, message_id=status_msg.message_id)

# ─── Фоновый мониторинг прогресса ──────────────────────────────────────────
def monitor_progress(user_id):
    task_data = active_tasks[user_id]
    task_id = task_data['task_id']
    msg_id = task_data['msg_id']
    prompt = task_data.get('prompt', '')
    max_attempts = 120  # Максимум 6 минут ожидания

    for _ in range(max_attempts):
        time.sleep(3)  # Опрос каждые 3 секунды
        
        try:
            info = video_service.get_status(task_id)
            if not info:
                continue

            status = info.get('status', 'unknown')
            progress = info.get('progress', 0)
            active_tasks[user_id]['status'] = status

            # Формируем прогресс-бар
            bar_len = 20
            filled = int((progress / 100) * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)

            emojis = {
                "queued": "⏳",
                "in_progress": "⚙️",
                "downloading": "⬇️",
                "completed": "✅",
                "failed": "❌",
                "error": "❌"
            }
            emoji = emojis.get(status, "⏳")
            status_text = f"{emoji} **Генерация видео**\n\n`{prompt[:30]}...`\n\n[{bar}] {progress:.0f}%"

            # Обновляем сообщение в Telegram (игнорируем ошибки, если текст не изменился)
            try:
                bot.edit_message_text(status_text, chat_id=user_id, message_id=msg_id, parse_mode="Markdown")
            except Exception:
                pass

            # ✅ Генерация завершена
            if status == "completed":
                time.sleep(2)  # Гарантия, что файл полностью записан на диск
                file_path = info.get('file_path')

                if file_path and os.path.exists(file_path):
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    logging.info(f"📤 Отправка видео ({file_size_mb:.2f} MB)...")

                    try:
                        with open(file_path, 'rb') as f:
                            bot.send_video(
                                user_id,
                                f,
                                caption="✅ **Твоё видео готово!**",
                                parse_mode="Markdown",
                                timeout=120,              # ⬅️ Увеличенный таймаут
                                supports_streaming=True   # ⬅️ Оптимизация для видео
                            )
                        logging.info("📤 Видео успешно отправлено!")
                    except Exception as e:
                        logging.error(f"Ошибка отправки: {e}")
                        # Повторная попытка при сетевых сбоях
                        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                            time.sleep(5)
                            try:
                                with open(file_path, 'rb') as f:
                                    bot.send_video(user_id, f, caption="✅ **Видео готово!**", parse_mode="Markdown", timeout=120)
                                logging.info("📤 Отправлено со второй попытки!")
                            except Exception as retry_e:
                                logging.error(f"Ошибка повторной отправки: {retry_e}")
                                bot.send_message(user_id, "❌ Сервер Telegram перегружен. Попробуйте позже.")
                        else:
                            bot.send_message(user_id, f"❌ Ошибка отправки файла: {e}")
                else:
                    bot.send_message(user_id, "❌ Файл не найден или повреждён. Попробуйте ещё раз.")

                # Очистка состояния
                if user_id in active_tasks:
                    del active_tasks[user_id]
                return

            # ❌ Ошибка генерации
            elif status in ("failed", "error"):
                error_msg = info.get('error', 'Неизвестная ошибка')
                bot.edit_message_text(
                    f"❌ **Ошибка генерации**\n\n{error_msg}",
                    chat_id=user_id,
                    message_id=msg_id,
                    parse_mode="Markdown"
                )
                if user_id in active_tasks:
                    del active_tasks[user_id]
                return

        except Exception as e:
            logging.error(f"⚠️ Ошибка в monitor_progress: {e}")
            continue

    # ⏱️ Превышено время ожидания
    bot.send_message(user_id, "⏱️ Превышено время ожидания. Попробуйте позже.")
    if user_id in active_tasks:
        del active_tasks[user_id]

# ─── Запуск ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    logging.info("🤖 Бот запущен и ждёт сообщений...")
    bot.infinity_polling()