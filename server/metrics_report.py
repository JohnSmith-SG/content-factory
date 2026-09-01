#!/usr/bin/env python3
"""Печатает метрики канала для скилла /channel-report:
живое число подписчиков + история ежедневных снимков (metrics.jsonl).

Read-only, без ИИ. Запускается на VPS через `vps.sh ssh 'python3 /opt/content-factory/metrics_report.py'`.
Токен бота читается из файла на сервере и наружу не выводится — печатается
только само число.
"""
import json
import os
import urllib.request

BASE = "/opt/content-factory"
CHANNEL = "@ai_pro_cg"
TOKEN = open(os.path.join(BASE, "secrets", "telegram_bot.token"), encoding="utf-8").read().strip()
METRICS_FILE = os.path.join(BASE, "logs", "metrics.jsonl")


def main():
    url = f"https://api.telegram.org/bot{TOKEN}/getChatMemberCount?chat_id={CHANNEL}"
    try:
        live = json.load(urllib.request.urlopen(url, timeout=20)).get("result")
    except Exception as e:
        live = None
        print(f"LIVE_ERROR: {e}")
    print(f"LIVE_SUBSCRIBERS: {live}")

    print("=== SNAPSHOTS ===")
    if os.path.exists(METRICS_FILE):
        print(open(METRICS_FILE, encoding="utf-8").read().rstrip())
    else:
        print("(снимков пока нет — bot_listener ещё не переваливал дату после деплоя)")


if __name__ == "__main__":
    main()
