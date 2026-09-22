import os
import re
import json
import urllib.request
from http.server import BaseHTTPRequestHandler
from datetime import datetime

# 🛠️ CONFIG (Vercel Environment Variables se aayega)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")  # Postgres URL (optional)
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
HAS_DB = bool(DATABASE_URL)

# ---------- DATABASE ----------
def get_db():
    import psycopg2
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    if not HAS_DB:
        return
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, username TEXT,
            first_name TEXT, joined_date TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS usage (
            id SERIAL PRIMARY KEY, user_id BIGINT,
            url TEXT, timestamp TEXT)""")
        conn.commit(); conn.close()
    except Exception as e:
        print("init_db err:", e)

def add_user(uid, uname, fname):
    if not HAS_DB: return
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("""INSERT INTO users (user_id, username, first_name, joined_date)
                     VALUES (%s,%s,%s,%s)
                     ON CONFLICT (user_id) DO NOTHING""",
                  (uid, uname, fname, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit(); conn.close()
    except Exception as e:
        print("add_user err:", e)

def log_usage(uid, url):
    if not HAS_DB: return
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("INSERT INTO usage (user_id, url, timestamp) VALUES (%s,%s,%s)",
                  (uid, url, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit(); conn.close()
    except Exception as e:
        print("log_usage err:", e)

def get_stats():
    if not HAS_DB: return (0, 0)
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users"); u = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM usage"); m = c.fetchone()[0]
        conn.close(); return (u, m)
    except: return (0, 0)

def get_all_users():
    if not HAS_DB: return []
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        rows = [r[0] for r in c.fetchall()]
        conn.close(); return rows
    except: return []

# ---------- TELEGRAM API ----------
def send_api_request(method, data=None, files=None):
    url = API_URL + method
    try:
        if files:
            boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
            parts = []
            if data:
                for k, v in data.items():
                    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            for k, (fname, fbytes) in files.items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
                if isinstance(fbytes, str): fbytes = fbytes.encode('utf-8')
                parts.append(fbytes); parts.append(b'\r\n')
            parts.append(f'--{boundary}--\r\n'.encode())
            payload = b''.join(parts)
            headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
            req = urllib.request.Request(url, data=payload, headers=headers)
        else:
            payload = json.dumps(data).encode() if data else None
            headers = {'Content-Type': 'application/json'} if data else {}
            req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"API Error ({method}): {e}")
        return None

# ---------- CORE ENGINE ----------
def remove_obfuscation(html_text: str) -> str:
    try:
        html_text = re.sub(r'\\x([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), html_text)
        html_text = re.sub(r'\\u([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), html_text)
        m = re.search(r'eval\(["\'](.+?)["\']\)', html_text, re.DOTALL)
        if m: html_text = m.group(1)
        return html_text
    except Exception as e:
        return f"❌ Failed to decode: {e}"

def fetch_and_decode(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            return remove_obfuscation(r.read().decode('utf-8', errors='ignore'))
    except Exception as e:
        return f"❌ Fetch error: {e}"

# ---------- KEYBOARD ----------
def get_keyboard(is_admin=False):
    btns = [[{"text": "🔗 Uʀʟ Tᴏ Hᴛᴍʟ"}, {"text": "📊 Sᴛᴀᴛs"}]]
    if is_admin:
        btns.append([{"text": "📢 Bʀᴏᴀᴅᴄᴀsᴛ"}])
    return {"keyboard": btns, "resize_keyboard": True}

# ---------- MESSAGE HANDLER ----------
# Broadcast state ko DB me store karenge (serverless me memory persist nahi hoti)
# Simple trick: /broadcast command se direct message bhejo
def handle_message(msg):
    chat_id = msg['chat']['id']
    text = (msg.get('text') or '').strip()
    user = msg.get('from', {})
    is_admin = (chat_id == ADMIN_ID)

    add_user(chat_id, user.get('username', ''), user.get('first_name', 'Usᴇʀ'))

    if text == "/start":
        welcome = (
            "╔════════════════════╗\n"
            "   🌐 Uʀʟ Tᴏ Hᴛᴍʟ Bᴏᴛ\n"
            "╚════════════════════╝\n\n"
            "📌 Sᴇɴᴅ A Wᴇʙsɪᴛᴇ Uʀʟ Tᴏ Sᴛᴀʀᴛ!\n"
            "🔗 Exᴀᴍᴘʟᴇ: https://example.com"
        )
        send_api_request("sendMessage", {"chat_id": chat_id, "text": welcome, "reply_markup": get_keyboard(is_admin)})
        return

    if text == "🔗 Uʀʟ Tᴏ Hᴛᴍʟ":
        send_api_request("sendMessage", {"chat_id": chat_id, "text": "🌐 Sᴇɴᴅ A Uʀʟ Sᴛᴀʀᴛɪɴɢ Wɪᴛʜ http:// ᴏʀ https://"})
        return

    if text == "📊 Sᴛᴀᴛs":
        u, m = get_stats()
        send_api_request("sendMessage", {"chat_id": chat_id, "text": f"📊 Bᴏᴛ Sᴛᴀᴛs:\n👥 Usᴇʀs: {u}\n⚡ Usᴀɢᴇ: {m}"})
        return

    # Broadcast: /broadcast <message>
    if is_admin and text.startswith("/broadcast "):
        bmsg = text[len("/broadcast "):]
        count = 0
        for uid in get_all_users():
            if send_api_request("sendMessage", {"chat_id": uid, "text": bmsg}):
                count += 1
        send_api_request("sendMessage", {"chat_id": chat_id, "text": f"✅ Bʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ {count} ᴜsᴇʀs ᴄᴏᴍᴘʟᴇᴛᴇ!"})
        return

    # URL processing
    if text.startswith("http://") or text.startswith("https://"):
        log_usage(chat_id, text)
        send_api_request("sendMessage", {"chat_id": chat_id, "text": "⏳ Fᴇᴛᴄʜɪɴɢ... [30%]"})

        html_data = fetch_and_decode(text)

        if html_data.startswith("❌"):
            send_api_request("sendMessage", {"chat_id": chat_id, "text": f"❌ Eʀʀᴏʀ:\n{html_data}"})
            return

        file_name = "extracted.html"
        file_bytes = html_data.encode('utf-8')
        size_kb = round(len(file_bytes) / 1024, 2)

        caption = (
            f"✅ Hᴛᴍʟ Exᴛʀᴀᴄᴛɪᴏɴ Cᴏᴍᴘʟᴇᴛᴇ!\n\n"
            f"📁 Fɪʟᴇ: <code>{file_name}</code>\n"
            f"📦 Sɪᴢᴇ: <code>{size_kb} KB</code>\n\n"
            f"⚡ Exᴛʀᴀᴄᴛᴇᴅ Sᴜᴄᴄᴇssғᴜʟʟʏ"
        )
        send_api_request(
            "sendDocument",
            {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            {"document": (file_name, file_bytes)}
        )
        return

    if text:
        send_api_request("sendMessage", {"chat_id": chat_id, "text": "❌ Iɴᴠᴀʟɪᴅ Cᴏᴍᴍᴀɴᴅ ᴏʀ Uʀʟ."})

# ---------- VERCEL HANDLER ----------
init_db()

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            update = json.loads(body.decode('utf-8'))
            if "message" in update:
                handle_message(update["message"])
        except Exception as e:
            print("handler err:", e)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'URL2HTML Bot is running!')
