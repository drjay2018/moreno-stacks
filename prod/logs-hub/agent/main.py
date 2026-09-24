import os
import time
import threading
import psycopg2
import requests
import google.generativeai as genai
from fastapi import FastAPI
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-flash-latest")

app = FastAPI()


class LogEntry(BaseModel):
    app: str
    level: str
    message: str


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def find_known_resolution(message: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT resolution FROM logs WHERE resolved = TRUE AND message ILIKE %s LIMIT 1",
        (f"%{message[:50]}%",),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def save_log(app_name, level, message, resolved=False, resolution=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (app_name, level, message, resolved, resolution) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (app_name, level, message, resolved, resolution),
    )
    log_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return log_id


def ask_gemini(message: str):
    prompt = (
        "Sos un asistente de soporte técnico. Analizá este error de una "
        f"aplicación Python:\n\n{message}\n\n"
        "Si podés identificar la causa y solución con alta confianza, "
        "respondé EXACTAMENTE en este formato:\nRESUELTO: <causa y solución breve>\n\n"
        "Si no estás seguro o falta contexto, respondé EXACTAMENTE:\n"
        "DUDA: <qué información te falta>"
    )
    response = model.generate_content(prompt)
    return response.text.strip()


def ask_jasser(log_id: int, app_name: str, message: str, gemini_note: str):
    text = (
        f"🔴 Error nuevo en {app_name} (log #{log_id})\n\n{message}\n\n"
        f"Gemini no está seguro: {gemini_note}\n\n"
        f"Respondé a este mensaje con la solución."
    )
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
    )
    data = resp.json()
    if not data.get("ok"):
        print(f"ERROR Telegram: {data}")
        raise Exception(f"Telegram rechazó el mensaje: {data}")
    telegram_message_id = data["result"]["message_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO telegram_pending (telegram_message_id, log_id) VALUES (%s,%s)",
        (telegram_message_id, log_id),
    )
    conn.commit()
    cur.close()
    conn.close()


@app.post("/log-error")
def receive_log(entry: LogEntry):
    known = find_known_resolution(entry.message)
    if known:
        save_log(entry.app, entry.level, entry.message, resolved=True, resolution=known)
        return {"status": "resuelto_automaticamente", "resolution": known}

    gemini_answer = ask_gemini(entry.message)

    if gemini_answer.startswith("RESUELTO:"):
        resolution = gemini_answer.replace("RESUELTO:", "").strip()
        save_log(entry.app, entry.level, entry.message, resolved=True, resolution=resolution)
        return {"status": "resuelto_por_gemini", "resolution": resolution}

    note = gemini_answer.replace("DUDA:", "").strip()
    log_id = save_log(entry.app, entry.level, entry.message, resolved=False)
    ask_jasser(log_id, entry.app, entry.message, note)
    return {"status": "consultando_a_jasser", "log_id": log_id}


def handle_jasser_reply(replied_id, jasser_response):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT log_id FROM telegram_pending WHERE telegram_message_id = %s",
        (replied_id,),
    )
    row = cur.fetchone()
    if row:
        log_id = row[0]
        cur.execute(
            "UPDATE logs SET resolved = TRUE, resolution = %s WHERE id = %s",
            (jasser_response, log_id),
        )
        conn.commit()
    cur.close()
    conn.close()


def poll_telegram():
    last_update_id = 0
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 30},
                timeout=35,
            )
            for update in resp.json().get("result", []):
                last_update_id = update["update_id"]
                message = update.get("message", {})
                reply_to = message.get("reply_to_message")
                if reply_to:
                    handle_jasser_reply(reply_to["message_id"], message.get("text", ""))
        except Exception as e:
            print(f"Error consultando Telegram: {e}")
            time.sleep(5)


@app.on_event("startup")
def start_polling():
    threading.Thread(target=poll_telegram, daemon=True).start()
