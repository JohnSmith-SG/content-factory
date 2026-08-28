#!/usr/bin/env python3
"""Content-factory scheduled publisher.
Reads the earliest not-yet-sent post from queue/, publishes it to the
Telegram channel via Bot API, and moves it to sent/. No AI calls here —
pure mechanical Telegram API calls against an already-approved queue.
"""
import json
import os
import sys
import glob
import shutil
import hashlib
import datetime
import urllib.request
import urllib.parse

BASE = "/opt/content-factory"
QUEUE_DIR = os.path.join(BASE, "queue")
IMAGES_DIR = os.path.join(BASE, "images")
SENT_DIR = os.path.join(BASE, "sent")
LOG_FILE = os.path.join(BASE, "logs", "publish.log")
TOKEN_FILE = os.path.join(BASE, "secrets", "telegram_bot.token")
ID_MAP_FILE = os.path.join(BASE, "id_map.json")

# --- настройки развёртывания: подставить свои перед запуском ---
CHAT_ID = "@ai_pro_cg"          # публичный канал
BOT_USERNAME = "ai_pro_cg_bot"  # для deep link кнопки «English version»

# карточка актуального поста на карьерном сайте (tsurtsumiya.netlify.app, раздел AI:stack)
GIST_ID = "dc74543025fd9d12733280b8e4686830"
GIST_TOKEN_FILE = os.path.join(BASE, "secrets", "github_gist.token")

def short_id_for(filename):
    return hashlib.sha256(filename.encode("utf-8")).hexdigest()[:10]

def register_id_map(filename, sid):
    id_map = {}
    if os.path.exists(ID_MAP_FILE):
        try:
            id_map = json.load(open(ID_MAP_FILE, encoding="utf-8"))
        except Exception:
            id_map = {}
    id_map[sid] = filename
    json.dump(id_map, open(ID_MAP_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def log(msg):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def build_caption_and_followup(text):
    paras = text.split("\n\n")
    title = paras[0]
    first = paras[1]
    rest = paras[2:]
    caption = f"<b>{esc(title)}</b>\n\n{esc(first)}\n\n\U0001F447 Продолжение"
    followup = "⠀\n\n" + "\n\n".join(esc(p) for p in rest)
    return caption, followup

def update_career_card(post, post_date, basename, message_id, text):
    """Обновляет секретный gist latest.json — источник данных для «живой» карточки
    актуального поста в разделе AI:stack на карьерном сайте.
    Никогда не бросает исключение: сбой обновления не должен ронять публикацию."""
    try:
        if not os.path.exists(GIST_TOKEN_FILE):
            log("gist token missing, skipping career-card update")
            return
        gist_token = open(GIST_TOKEN_FILE, encoding="utf-8").read().strip()

        paras = text.split("\n\n")
        title = paras[0]
        second = paras[1] if len(paras) > 1 else ""
        excerpt = second[:220] + ("…" if len(second) > 220 else "")

        payload = {
            "date": post_date.isoformat(),
            "title": title,
            "excerpt": excerpt,
            "image": f"https://raw.githubusercontent.com/JohnSmith-SG/content-factory/main/images/{basename.replace('-social-content', '')}.jpg",
            "link": f"https://t.me/ai_pro_cg/{message_id}",
            "en": bool(post.get("platforms", {}).get("facebook", {}).get("content")),
        }
        body = json.dumps({
            "files": {"latest.json": {"content": json.dumps(payload, ensure_ascii=False, indent=2)}}
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.github.com/gists/{GIST_ID}", data=body, method="PATCH"
        )
        req.add_header("Authorization", f"token {gist_token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "content-factory")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            log(f"career-card gist updated (HTTP {resp.status})")
    except Exception as e:
        log(f"WARNING: career-card gist update failed: {e}")


def api_call(token, method, data=None, files=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:
        # multipart/form-data for sendPhoto
        boundary = "----cfboundary"
        body = b""
        for key, value in (data or {}).items():
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8")
        for key, (filename, content) in files.items():
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode("utf-8")
            body += content
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data or {}).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    if not os.path.exists(TOKEN_FILE):
        log("ERROR: token file missing")
        sys.exit(1)
    token = open(TOKEN_FILE, encoding="utf-8").read().strip()

    today = datetime.datetime.now(datetime.timezone.utc).date()

    files = sorted(glob.glob(os.path.join(QUEUE_DIR, "*.json")))
    if not files:
        log("No posts in queue. Nothing to do.")
        return

    post_path = files[0]
    basename = os.path.splitext(os.path.basename(post_path))[0]
    # date prefix is first 10 chars: YYYY-MM-DD
    date_str = os.path.basename(post_path)[:10]
    try:
        post_date = datetime.date.fromisoformat(date_str)
    except ValueError:
        post_date = today  # if unparsable, don't block on date guard

    if post_date > today:
        log(f"Earliest queued post {basename} is dated {post_date}, in the future. Skipping run.")
        return

    post = json.load(open(post_path, encoding="utf-8"))
    if post.get("status") != "approved":
        log(f"ERROR: {basename} status is '{post.get('status')}', not 'approved'. Refusing to publish. Manual check needed.")
        return

    text = post["platforms"]["telegram"]["content"]
    caption, followup = build_caption_and_followup(text)

    image_candidates = glob.glob(os.path.join(IMAGES_DIR, basename.replace("-social-content", "") + ".*"))
    if not image_candidates:
        log(f"ERROR: no image found for {basename}. Refusing to publish without image.")
        return
    image_path = image_candidates[0]

    log(f"Publishing {basename} (image: {os.path.basename(image_path)})")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    post_filename = os.path.basename(post_path)
    sid = short_id_for(post_filename)
    register_id_map(post_filename, sid)
    keyboard = json.dumps({
        "inline_keyboard": [[{"text": "\U0001F1EC\U0001F1E7 English version", "url": f"https://t.me/{BOT_USERNAME}?start=en_{sid}"}]]
    })

    resp1 = api_call(
        token,
        "sendPhoto",
        data={"chat_id": CHAT_ID, "parse_mode": "HTML", "caption": caption, "reply_markup": keyboard},
        files={"photo": (os.path.basename(image_path), image_bytes)},
    )
    if not resp1.get("ok"):
        log(f"ERROR sendPhoto failed: {resp1}")
        return
    log(f"sendPhoto ok, message_id={resp1['result']['message_id']}")

    resp2 = api_call(
        token,
        "sendMessage",
        data={"chat_id": CHAT_ID, "parse_mode": "HTML", "text": followup},
    )
    if not resp2.get("ok"):
        log(f"ERROR sendMessage (followup) failed: {resp2}")
        return
    log(f"sendMessage ok, message_id={resp2['result']['message_id']}")

    link = f"https://t.me/ai_pro_cg/{resp1['result']['message_id']}"
    log(f"Published successfully: {link}")

    update_career_card(post, post_date, basename, resp1["result"]["message_id"], text)

    shutil.move(post_path, os.path.join(SENT_DIR, os.path.basename(post_path)))
    shutil.move(image_path, os.path.join(SENT_DIR, os.path.basename(image_path)))
    log(f"Moved {basename} to sent/")

if __name__ == "__main__":
    main()
