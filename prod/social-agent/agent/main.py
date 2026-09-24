import os
import time
import shutil
import subprocess
import requests
import google.generativeai as genai
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

INCOMING = Path("/data/incoming")
PROCESSED = Path("/data/processed")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-flash-latest")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv"}


def process_image(path: Path) -> Path:
    out_path = PROCESSED / f"{path.stem}_ig.jpg"
    img = Image.open(path).convert("RGB")

    target_ratio = 1.0
    w, h = img.size
    current_ratio = w / h

    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif current_ratio < target_ratio:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    img.thumbnail((1080, 1080))
    img.save(out_path, "JPEG", quality=90)
    return out_path


def process_video(path: Path) -> Path:
    out_path = PROCESSED / f"{path.stem}_reel.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(path),
            "-vf", "crop=ih*9/16:ih,scale=1080:1920",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            str(out_path),
        ],
        check=True,
    )
    return out_path


def generate_caption(filename: str) -> str:
    prompt = (
        f"Sos el community manager de una inmobiliaria en República Dominicana. "
        f"Generá un caption corto y atractivo para Instagram/Facebook para una "
        f"publicación llamada '{filename}'. Incluí 3-5 hashtags relevantes al "
        f"sector inmobiliario dominicano. Respondé solo el texto del caption, nada más."
    )
    response = model.generate_content(prompt)
    return response.text.strip()


def send_for_approval(media_path: Path, caption: str):
    is_video = media_path.suffix.lower() == ".mp4"
    endpoint = "sendVideo" if is_video else "sendPhoto"
    field = "video" if is_video else "photo"

    with open(media_path, "rb") as f:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{endpoint}",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": (
                    f"📱 Nueva publicación lista\n\n{caption}\n\n"
                    f"Respondé 'SI' para publicar, o escribí un caption nuevo."
                ),
            },
            files={field: f},
        )
    print(f"Enviado a Telegram: {resp.json().get('ok')}")


class Handler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        time.sleep(2)  # esperar a que termine de copiarse el archivo

        ext = path.suffix.lower()
        try:
            if ext in IMAGE_EXT:
                processed = process_image(path)
            elif ext in VIDEO_EXT:
                processed = process_video(path)
            else:
                print(f"Extensión no soportada: {path.name}")
                return

            caption = generate_caption(path.stem)
            send_for_approval(processed, caption)
            shutil.move(str(path), str(PROCESSED / f"_original_{path.name}"))

        except Exception as e:
            print(f"Error procesando {path.name}: {e}")


if __name__ == "__main__":
    INCOMING.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    observer = Observer()
    observer.schedule(Handler(), str(INCOMING), recursive=False)
    observer.start()
    print(f"Vigilando {INCOMING}...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
