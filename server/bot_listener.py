#!/usr/bin/env python3
"""Content-factory Telegram bot listener (long polling).
Handles two things, all mechanical -- no AI calls:
  1. The "English version" button under a post is a url button opening a
     Telegram deep link (t.me/<bot>?start=en_<short_id>) -- this actually
     switches the user's screen to the private chat with the bot (unlike
     the old callback_data approach, which fired silently server-side with
     no visible transition). On /start with that payload: check channel
     subscription live via getChatMember and DM the English text right
     away, or ask the user to subscribe first. No persistent opt-in list --
     subscription is checked fresh on every click, so there's nothing to
     go stale if someone unsubscribes later.
  2. Comments in the linked discussion group -> delete any comment from
     someone who isn't a channel subscriber (bot must be admin there with
     delete-messages rights).
"""
import json
import os
import time
import glob
import hashlib
import urllib.request
import urllib.parse
import datetime

BASE = "/opt/content-factory"
QUEUE_DIR = os.path.join(BASE, "queue")
SENT_DIR = os.path.join(BASE, "sent")
TOKEN_FILE = os.path.join(BASE, "secrets", "telegram_bot.token")
ID_MAP_FILE = os.path.join(BASE, "id_map.json")
OFFSET_FILE = os.path.join(BASE, "update_offset.txt")
LOG_FILE = os.path.join(BASE, "logs", "bot_listener.log")
COMMENTS_LOG_FILE = os.path.join(BASE, "logs", "comments_for_review.jsonl")
# --- настройки развёртывания: подставить свои перед запуском на сервере ---
CHANNEL = "@ai_pro_cg"                 # публичный канал
DISCUSSION_GROUP_ID = -100_0000000000  # id связанной группы-обсуждения

TOKEN = open(TOKEN_FILE, encoding="utf-8").read().strip()
API = f"https://api.telegram.org/bot{TOKEN}"


def log(msg):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def api_call(method, data):
    url = f"{API}/{method}"
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=35) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return default
    return default


def get_offset():
    if os.path.exists(OFFSET_FILE):
        return int(open(OFFSET_FILE).read().strip() or 0)
    return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


def is_subscribed(user_id):
    resp = api_call("getChatMember", {"chat_id": CHANNEL, "user_id": user_id})
    if not resp.get("ok"):
        log(f"getChatMember failed for {user_id}: {resp}")
        return False
    status = resp["result"].get("status")
    return status in ("member", "administrator", "creator")


def short_id_for(filename):
    return hashlib.sha256(filename.encode("utf-8")).hexdigest()[:10]


def find_post_by_short_id(sid):
    id_map = load_json(ID_MAP_FILE, {})
    filename = id_map.get(sid)
    if not filename:
        return None
    for d in (QUEUE_DIR, SENT_DIR):
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


def log_comment_for_review(msg, from_user, is_anonymous_admin=False):
    """Append a legitimate subscriber comment to a plain log for later
    analysis in a live Claude Code session -- no judgment happens here,
    this is purely mechanical data collection. Kept intentionally raw
    (not pre-filtered for "looks like criticism") since deciding that
    requires actual reasoning, which only happens in a live session.
    """
    entry = {
        "logged_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "message_id": msg["message_id"],
        "user_id": from_user["id"],
        "username": from_user.get("username"),
        "first_name": from_user.get("first_name"),
        "is_anonymous_admin": is_anonymous_admin,
        "text": msg.get("text") or msg.get("caption") or "",
        "reply_to_message_id": (msg.get("reply_to_message") or {}).get("message_id"),
        "date": msg.get("date"),
    }
    with open(COMMENTS_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def moderate_comment(msg):
    """Discussion-group comment moderation: only channel subscribers may
    write. Deletes the comment of anyone who isn't. Skips anything that
    isn't a plain user comment (auto-forwarded channel post copy, service
    messages) -- those have no real 'from' user to check.

    Anonymous admin posts (Telegram shows these as from the pseudo-account
    "GroupAnonymousBot" whenever an admin -- here, the channel owner -- has
    "remain anonymous" on) are a separate case: is_bot is true for that
    pseudo-account, but only actual group admins can post anonymously, so
    it's always a legitimate comment worth logging -- never delete it, and
    don't skip it just because it looks bot-shaped.

    Legitimate subscriber comments (including anonymous-admin ones) get
    logged for later review (see log_comment_for_review) -- this is the
    raw material for the self-improvement mechanism discussed 2026-08-27.
    """
    from_user = msg.get("from")
    if not from_user:
        return  # service message with no real sender at all
    if msg.get("is_automatic_forward"):
        return  # the channel post copy itself, not a comment
    if from_user.get("username") == "GroupAnonymousBot":
        log_comment_for_review(msg, from_user, is_anonymous_admin=True)
        return
    if from_user.get("is_bot"):
        return  # some other bot, not a real comment
    user_id = from_user["id"]
    if is_subscribed(user_id):
        log_comment_for_review(msg, from_user)
        return
    resp = api_call("deleteMessage", {"chat_id": DISCUSSION_GROUP_ID, "message_id": msg["message_id"]})
    if resp.get("ok"):
        log(f"Deleted comment from non-subscriber {user_id} (@{from_user.get('username')})")
    else:
        log(f"Failed to delete comment from {user_id}: {resp}")


def handle_start_en(user_id, sid):
    if not is_subscribed(user_id):
        api_call("sendMessage", {
            "chat_id": user_id,
            "text": "Похоже, ты ещё не подписан(а) на канал @ai_pro_cg — подпишись и снова нажми кнопку English version под постом.",
        })
        return

    post_path = find_post_by_short_id(sid)
    if not post_path:
        api_call("sendMessage", {"chat_id": user_id, "text": "Не нашла текст для этого поста."})
        log(f"/start en_{sid} from {user_id}: unknown short id")
        return

    post = json.load(open(post_path, encoding="utf-8"))
    english_text = post.get("platforms", {}).get("facebook", {}).get("content", "")
    if not english_text:
        api_call("sendMessage", {"chat_id": user_id, "text": "Английский текст не найден."})
        return

    resp = api_call("sendMessage", {"chat_id": user_id, "text": english_text})
    if resp.get("ok"):
        log(f"Sent English version of {sid} to user {user_id} (deep link)")
    else:
        log(f"Failed to DM user {user_id} for {sid}: {resp}")


def handle_message(msg):
    chat = msg.get("chat", {})
    if chat.get("id") == DISCUSSION_GROUP_ID:
        moderate_comment(msg)
        return
    if chat.get("type") != "private":
        return  # ignore any other group/channel text, only private DMs to the bot matter
    user_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not text.startswith("/start"):
        return
    payload = text[len("/start"):].strip()
    if payload.startswith("en_"):
        handle_start_en(user_id, payload[len("en_"):])


def poll_loop():
    log("Bot listener started.")
    offset = get_offset()
    while True:
        try:
            resp = api_call("getUpdates", {"offset": offset, "timeout": 30})
        except Exception as e:
            log(f"getUpdates error: {e}")
            time.sleep(5)
            continue

        if not resp.get("ok"):
            log(f"getUpdates not ok: {resp}")
            time.sleep(5)
            continue

        for update in resp["result"]:
            offset = update["update_id"] + 1
            if "message" in update:
                handle_message(update["message"])
            save_offset(offset)


if __name__ == "__main__":
    poll_loop()
