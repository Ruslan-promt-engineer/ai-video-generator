# video_service.py
import os
import time
import threading
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, Optional
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
load_dotenv()

class VideoService:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            raise ValueError("❌ API_KEY не найден в .env")
        self.base_url = "https://api.proxyapi.ru/openai/v1"
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self.video_dir = Path("generated_videos")
        self.video_dir.mkdir(exist_ok=True)
        self.tasks: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def create_task(self, prompt: str, duration: str = "4", model: str = "sora-2") -> str:
        payload = {"model": model, "prompt": prompt, "seconds": duration}
        resp = requests.post(f"{self.base_url}/videos", json=payload, headers=self.headers)
        resp.raise_for_status()
        task_id = resp.json()["id"]
        
        with self._lock:
            self.tasks[task_id] = {"status": "queued", "progress": 0.0, "file_path": None, "error": None, "prompt": prompt}
        
        threading.Thread(target=self._monitor_task, args=(task_id,), daemon=True).start()
        logging.info(f"📦 Задача создана: {task_id}")
        return task_id

    def _monitor_task(self, task_id: str):
        while True:
            time.sleep(5)
            try:
                resp = requests.get(f"{self.base_url}/videos/{task_id}", headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status", "unknown")
                progress = data.get("progress", 0.0)

                with self._lock:
                    self.tasks[task_id]["status"] = status
                    self.tasks[task_id]["progress"] = progress

                if status == "failed":
                    with self._lock:
                        self.tasks[task_id]["error"] = data.get("error", {}).get("message", "Unknown")
                    logging.error(f"❌ {task_id} failed")
                    break

                if status in ("completed", "succeeded", "success"):
                    with self._lock:
                        self.tasks[task_id]["status"] = "downloading"
                    self._download_video(task_id)
                    break
            except Exception as e:
                logging.error(f"⚠️ Ошибка опроса {task_id}: {e}")
                with self._lock:
                    self.tasks[task_id]["status"] = "error"
                    self.tasks[task_id]["error"] = str(e)
                break

    def _clean_old_videos(self, retention_hours: int = 48):
        """Удаляет видеофайлы старше указанного времени (по умолчанию 48 часов)"""
        try:
            current_time = time.time()
            retention_seconds = retention_hours * 3600  # 48 часов = 172800 секунд
            
            for filepath in self.video_dir.glob("*.mp4"):
                file_age = current_time - filepath.stat().st_mtime
                if file_age > retention_seconds:
                    filepath.unlink()
                    logging.info(f"🗑️ Удалено старое видео: {filepath.name} (возраст: {file_age/3600:.1f} ч)")
        except Exception as e:
            logging.error(f"❌ Ошибка при очистке старых видео: {e}")

    def _download_video(self, task_id: str):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prompt_snippet = self.tasks[task_id]["prompt"][:25].replace(" ", "_")
            filename = self.video_dir / f"vid_{task_id[:8]}_{timestamp}_{prompt_snippet}.mp4"

            resp = requests.get(f"{self.base_url}/videos/{task_id}/content", headers=self.headers, stream=True)
            resp.raise_for_status()

            with open(filename, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # 🛡️ Автоочистка старых видео после успешного сохранения
            self._clean_old_videos(retention_hours=48)

            with self._lock:
                self.tasks[task_id]["file_path"] = str(filename)
                self.tasks[task_id]["status"] = "completed"
            logging.info(f"📁 Сохранено: {filename}")

        except Exception as e:
            logging.error(f"❌ Ошибка скачивания {task_id}: {e}")
            with self._lock:
                self.tasks[task_id]["error"] = f"Download failed: {e}"
                self.tasks[task_id]["status"] = "error"

    def get_status(self, task_id: str) -> Optional[dict]:
        with self._lock:
            return self.tasks.get(task_id)

video_service = VideoService()