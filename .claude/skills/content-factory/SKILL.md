---
name: content-factory
description: Точка входа в проект content-factory — конвейер генерации и автопубликации постов для Telegram-канала на стыке искусственного интеллекта и корпоративного управления. Объясняет структуру репозитория, как запустить конвейер локально, как развернуть автопубликацию на сервере, где лежат секреты и что менять под свой канал. Используй при первом знакомстве с репозиторием или когда нужно развернуть проект у себя.
---

# Проект content-factory

Конвейер генерации и автопубликации постов для Telegram-канала на стыке
искусственного интеллекта и корпоративного управления. Сам выбирает
источник (следующий неиспользованный из `context/sources.md` или свежая
публикация по теме), пишет пост (русский для Telegram + английский для
Facebook), рисует картинку, проводит через содержательное ревью и
публикует в Telegram-канал — по одному посту в будний день, автоматически,
по расписанию на отдельном сервере.

## Структура репозитория

```
content-factory/
├── .claude/
│   ├── agents/          4 субагента конвейера (роли)
│   ├── skills/          скиллы: этот + операционные (см. ниже)
│   ├── scripts/vps.sh   обёртка доступа к серверу (пароль не светит)
│   └── deploy.md        как устроено развёртывание на VPS
├── context/             бренд-гайд, принципы письма, чек-лист ИИ-штампов,
│                        список источников для ресёрча
├── docs/                описание проекта, скриншоты
├── posts/               результат: JSON-файлы постов (draft→reviewed→
│                        approved→published)
├── images/              сгенерированные картинки (имя = имя поста)
├── server/              код, который крутится на VPS (publish.py,
│                        bot_listener.py, systemd/)
├── tmp/                  рабочий мусор (в git не идёт)
└── CLAUDE.md            рабочие правила проекта (расписание, нормы очереди)
```

## Скиллы проекта

| Скилл | Зачем |
|---|---|
| `content-pipeline` | оркестратор: проверить расписание и очередь, запустить нужных субагентов. **С этого начинается любая рабочая сессия.** |
| `new-post` | провести один новый пост от идеи до превью на согласование |
| `ku-ai-social` | превратить статью в JSON с постами (без публикации) |
| `governance-coach` | содержательное ревью черновика глазами директора по КУ |
| `telegram-publish` | механически опубликовать уже одобренный пост |

Субагенты (`.claude/agents/`): `content-researcher` → `image-generator` →
`governance-reviewer` → `telegram-publisher`. Ролевой + последовательный
конвейер, каждый шаг зависит от предыдущего. Контракт передачи —
путь к JSON-файлу в `posts/`, а не пересказ содержимого.

## Запуск конвейера локально

1. Нужен Claude Code и MCP-сервер **fal.ai** для генерации картинок.
   Сервер описан в `.mcp.json` (в репозитории), ключ туда **не пишется** —
   подставляется из переменной окружения `FAL_KEY`. Сам ключ храни в
   `.claude/secrets/fal.key` (в git не идёт) и грузи в `FAL_KEY` через
   профиль оболочки:
   `$env:FAL_KEY = (Get-Content "<путь>/.claude/secrets/fal.key" -Raw).Trim()`
   При первом запуске Claude Code попросит одобрить MCP-сервер из `.mcp.json`.
2. Войти в проект → вызвать скилл `content-pipeline`. Он сам проверит
   дату, глубину очереди и скажет, чего не хватает.
3. Пополнить очередь одним постом: `/new-post` (без аргументов —
   `content-researcher` сам выберет следующий источник из
   `context/sources.md` или найдёт свежую публикацию; можно задать ссылку
   или тему). Пройдёт ресёрч → картинку → ревью → автоправки, остановится
   один раз на HTML-превью, ждёт «да».
4. После «да» оркестратор вручную ставит посту `status: approved` и кладёт
   файл (JSON + картинку) в очередь на сервере (`vps.sh put ...`).

Статус поста в JSON: `draft → reviewed → approved → published`. `approved`
ставит только человек-оркестратор после одобренного превью — ни один
субагент этот статус сам не присваивает.

## Развёртывание автопубликации (сервер)

Подробно — `.claude/deploy.md`. Коротко: любой VPS с постоянным аптаймом,
пользователь `cfbot`, папка `/opt/content-factory/`, systemd-таймер по
будням в 04:30 UTC. На сервере ИИ нет — `publish.py` механически берёт
самый ранний одобренный пост из `queue/`, шлёт через Bot API, переносит в
`sent/`. Второй сервис `bot_listener.py` — кнопка «English version» и
модерация комментариев.

```
# на сервере, один раз
useradd -r -m -d /opt/content-factory cfbot
mkdir -p /opt/content-factory/{queue,sent,images,secrets,logs}
echo "<BOT_TOKEN>" > /opt/content-factory/secrets/telegram_bot.token
chmod 600 /opt/content-factory/secrets/telegram_bot.token
chown -R cfbot:cfbot /opt/content-factory
# скопировать server/publish.py, server/bot_listener.py в /opt/content-factory/
# скопировать server/systemd/* в /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cf-publish.timer cf-bot-listener.service
```

## Что менять под свой канал

- `server/publish.py` и `server/bot_listener.py`: `CHAT_ID` / `CHANNEL`
  (`@ai_pro_cg`), `DISCUSSION_GROUP_ID`, имя бота в deep link
  (`ai_pro_cg_bot`).
- `context/` — бренд-гайд, принципы письма, список источников под свою
  тему.
- `CLAUDE.md` — тема, площадки, расписание, нормы очереди.
- `.claude/scripts/vps.env` — адрес своего сервера и путь к файлу с
  паролем (скопировать из `vps.env.example`).

## Типовые задачи

- **Пополнить очередь** → `/new-post`, затем `vps.sh put` в `queue/`.
- **Проверить, что сервер жив** → `vps.sh ssh "systemctl list-timers
  cf-publish.timer && tail -n 20 /opt/content-factory/logs/publish.log"`.
- **Разобрать комментарии подписчиков** → `content-pipeline`, Шаг 0.
- **Поправить опубликованный пост** → через Bot API `editMessageText` /
  `editMessageCaption` по `message_id` из `publish.log`.
- **Обновить README** → после изменения структуры или логики конвейера
  синхронизировать `README.md` и этот скилл.

## Проверка перед публикацией репозитория

- `git status --ignored` — убедиться, что `.claude/secrets/`, `vps.env`,
  `settings.local.json`, `tmp/`, `deploy.local.md` в игноре.
- `git grep -niE '<ip сервера>|<имя vps>|telegram_bot\.token|fal\.key|passw'` —
  подставить свои реальные значения, убедиться что ничего лишнего не
  закоммичено.
- Открыть репозиторий в инкогнито — README и картинки отображаются.
