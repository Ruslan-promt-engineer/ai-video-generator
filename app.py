import os
from flask import Flask, render_template, request, jsonify, send_file
from video_service import video_service

app = Flask(__name__)

# Формируем ссылку на бота из .env
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")
TELEGRAM_LINK = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else ""

@app.route('/')
def index():
    # Передаем ссылку в шаблон
    return render_template('index.html', telegram_link=TELEGRAM_LINK)


@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'error': 'Промпт не может быть пустым'}), 400

    try:
        task_id = video_service.create_task(prompt)
        return jsonify({'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/<task_id>')
def status(task_id):
    info = video_service.get_status(task_id)
    if not info:
        return jsonify({'error': 'Задача не найдена'}), 404
    return jsonify(info)

@app.route('/api/download/<task_id>')
def download(task_id):
    info = video_service.get_status(task_id)
    if not info or info.get('status') != 'completed':
        return jsonify({'error': 'Видео ещё не готово или задача не найдена'}), 400

    file_path = info.get('file_path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Файл не найден на сервере'}), 404

    return send_file(file_path, as_attachment=True, download_name=f"ai_video_{task_id[:8]}.mp4")

if __name__ == '__main__':
    print("🌐 Запуск веб-приложения: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)