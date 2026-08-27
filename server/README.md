# server/ — код автопубликации для VPS

Крутится на отдельном сервере, не на рабочей машине и не в Claude Code.
ИИ здесь нет — только механические вызовы Telegram Bot API по уже
одобренной очереди.

| Файл | Что делает |
|---|---|
| `publish.py` | берёт самый ранний одобренный пост из `queue/`, публикует (`sendPhoto` + `sendMessage` + кнопка «English version»), переносит в `sent/`. Отказывается, если `status != approved` или дата не наступила. |
| `bot_listener.py` | long polling: deep link кнопки «English version» (проверка подписки + текст в личку) и модерация комментариев в группе-обсуждении. |
| `systemd/cf-publish.{service,timer}` | таймер `Mon..Fri 04:30 UTC` (= 7:30 МСК), `Persistent=true`. |
| `systemd/cf-bot-listener.service` | `Type=simple`, `Restart=always`. |

## Настройки развёртывания

В начале `publish.py` и `bot_listener.py` — константы с пометкой
«подставить свои»: `CHAT_ID` / `CHANNEL`, `BOT_USERNAME`,
`DISCUSSION_GROUP_ID`. В этом репозитории у них плейсхолдеры (кроме
публичного `@ai_pro_cg`); на реальном сервере стоят рабочие значения.
Токен бота — только в `/opt/content-factory/secrets/telegram_bot.token`
на сервере, в git не попадает.

## Установка — см. `.claude/skills/content-factory/SKILL.md`, раздел «Развёртывание».
