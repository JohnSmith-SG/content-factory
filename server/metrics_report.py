#!/usr/bin/env python3
"""Печатает метрики канала для скилла /channel-report:
живое число подписчиков + история ежедневных снимков (metrics.jsonl) +
счётчик комментариев подписчиков за периоды (comments_for_review.jsonl).

Read-only, без ИИ. Запускается на VPS через `vps.sh ssh 'python3 /opt/content-factory/metrics_report.py'`.
Токен бота читается из файла на сервере и наружу не выводится — печатается
только само число.
"""
import datetime
import json
import os
import urllib.request

BASE = "/opt/content-factory"
CHANNEL = "@ai_pro_cg"
TOKEN = open(os.path.join(BASE, "secrets", "telegram_bot.token"), encoding="utf-8").read().strip()
METRICS_FILE = os.path.join(BASE, "logs", "metrics.jsonl")
COMMENTS_FILE = os.path.join(BASE, "logs", "comments_for_review.jsonl")


def subscribers():
    url = f"https://api.telegram.org/bot{TOKEN}/getChatMemberCount?chat_id={CHANNEL}"
    try:
        live = json.load(urllib.request.urlopen(url, timeout=20)).get("result")
    except Exception as e:
        print(f"LIVE_ERROR: {e}")
        live = None
    print(f"LIVE_SUBSCRIBERS: {live}")

    print("=== SNAPSHOTS ===")
    if os.path.exists(METRICS_FILE):
        print(open(METRICS_FILE, encoding="utf-8").read().rstrip())
    else:
        print("(снимков пока нет — bot_listener ещё не переваливал дату после деплоя)")


def comments():
    """Комментарии за сутки / 7 / 30 дней. Отдельно total и 'от подписчиков'
    (без анонимных админ-комментов владельца)."""
    print("=== COMMENTS ===")
    if not os.path.exists(COMMENTS_FILE):
        print('{"note": "лог комментариев не найден"}')
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    total = {"1d": 0, "7d": 0, "30d": 0, "all": 0}
    subs = {"1d": 0, "7d": 0, "30d": 0, "all": 0}
    with open(COMMENTS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                ts = datetime.datetime.fromisoformat(e["logged_at"])
            except Exception:
                continue
            age_days = (now - ts).total_seconds() / 86400
            from_subscriber = not e.get("is_anonymous_admin")
            total["all"] += 1
            if from_subscriber:
                subs["all"] += 1
            for key, span in (("1d", 1), ("7d", 7), ("30d", 30)):
                if age_days <= span:
                    total[key] += 1
                    if from_subscriber:
                        subs[key] += 1
    print(f'{{"total": {json.dumps(total)}, "from_subscribers": {json.dumps(subs)}}}')


if __name__ == "__main__":
    subscribers()
    comments()
