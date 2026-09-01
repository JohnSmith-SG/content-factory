# Деплой content-factory — VPS-автопубликация

Реальная автономная публикация по расписанию — на отдельном VPS, не на
рабочей машине и не в сессии Claude Code. На сервере нет никакого ИИ,
только механические вызовы Telegram Bot API по уже одобренной очереди.

> Реальные адреса, пользователи и пути этого развёртывания в репозиторий
> не коммитятся. Локально они лежат в `.claude/deploy.local.md` и
> `.claude/scripts/vps.env` (оба в `.gitignore`). Ниже — плейсхолдеры
> `<VPS_IP>`, `<deploy-user>`, `<CHANNEL>`, `<BOT>`.

## Сервер

- Любой VPS с постоянным аптаймом. Ориентир: 1 vCPU, ~1 ГБ RAM,
  ~10 ГБ диска. ОС в описании — Ubuntu 24.04 LTS.
- Доступ по SSH (в этом развёртывании — по паролю; ключ предпочтительнее).
- **Таймзону сервера не трогаем** — расписание в systemd задаётся явно в
  UTC, поэтому локальная зона сервера роли не играет.

## Что развёрнуто на сервере

- Отдельный системный пользователь `cfbot` (не root), домашняя папка
  `/opt/content-factory/`.
- Структура: `queue/` (JSON + картинки одобренных постов, ждущих
  публикации), `sent/` (то же самое после публикации — просто
  перемещается сюда), `images/`, `secrets/telegram_bot.token`
  (права 600, владелец `cfbot`), `logs/`.
- `publish.py` — берёт самый ранний JSON из `queue/`, публикует через
  Telegram Bot API (`sendPhoto` + `sendMessage`, та же логика разбивки
  подпись/продолжение, что в `telegram-publish/SKILL.md`), переносит в
  `sent/`. Отказывается публиковать, если `status != "approved"` или дата
  поста ещё не наступила — защита от случайной публикации черновика.
- `cf-publish.service` (`Type=oneshot`, от `cfbot`) + `cf-publish.timer`
  (`OnCalendar=Mon..Fri 04:30:00 UTC` = 7:30 МСК, `Persistent=true` —
  наверстывает пропуск, если сервер был недоступен).
- `bot_listener.py` + `cf-bot-listener.service` (`Type=simple`,
  `Restart=always`, ~10 МБ памяти) — long polling `getUpdates`. Делает
  две вещи: обрабатывает deep link `t.me/<BOT>?start=en_<short_id>` от
  кнопки «English version» (проверяет подписку на `<CHANNEL>` через
  `getChatMember` и присылает английский текст в личку) и модерирует
  комментарии в группе-обсуждении (удаляет комментарии неподписчиков).

- `metrics_report.py` — read-only, по запросу (не сервис): печатает живое
  число подписчиков + историю снимков из `logs/metrics.jsonl`. Снимки раз
  в сутки пишет сам `bot_listener.py` (см. `daily_metrics_snapshot`).
  Используется скиллом `/channel-report`.

Исходники — в `server/` этого репозитория (`publish.py`, `bot_listener.py`,
`metrics_report.py`, `systemd/`). На сервере они лежат в `/opt/content-factory/`.

## Развернуть с нуля

Пошагово — в скилле проекта `.claude/skills/content-factory/SKILL.md`,
раздел «Развёртывание». Кратко:

1. Создать бота у @BotFather, получить токen; сделать бота админом канала
   и группы-обсуждения (право удаления сообщений).
2. На сервере: `useradd`, папка `/opt/content-factory/`, подпапки, положить
   токен в `secrets/telegram_bot.token` (chmod 600, chown cfbot).
3. Скопировать `server/publish.py`, `server/bot_listener.py`,
   `server/metrics_report.py` в `/opt/content-factory/`.
4. Скопировать `server/systemd/*` в `/etc/systemd/system/`,
   `systemctl daemon-reload`, `enable --now cf-publish.timer
   cf-bot-listener.service`.
5. Проверить: `systemctl list-timers cf-publish.timer`.

## Как пополнять очередь на сервере

Вручную, при каждой активной сессии в проекте — сервер сам ничего не
генерирует и не запрашивает. Передача файлов — обёртка
`.claude/scripts/vps.sh` (внутри — `pscp`):

```
vps.sh put posts/<файл>.json  /opt/content-factory/queue/<файл>.json
vps.sh put images/<файл>.jpg  /opt/content-factory/images/<файл>.jpg
```

После передачи — `chown cfbot:cfbot` на новые файлы. Норма очереди на
сервере — та же, что в основном `CLAUDE.md`: держать ≥5 постов вперёд.

## Как проверить статус

```
vps.sh ssh "systemctl list-timers cf-publish.timer"
vps.sh ssh "tail -n 30 /opt/content-factory/logs/publish.log"
```

## Что сознательно НЕ хранится на сервере / в git

- Ключи Claude/Anthropic — только на локальной машине.
- Токен бота — только в `/opt/content-factory/secrets/` на сервере,
  никогда в git.
- Статус публикации не пишется автоматически обратно в локальный
  `posts/*.json` — при следующем заходе в проект нужно вручную свериться
  с `sent/` на сервере и с реальным каналом.

## id_map.json (на сервере, не в git)

Сопоставление `short_id` (первые 10 символов SHA-256 от имени файла
поста) с реальным именем файла — нужно кнопке «English version», т.к.
параметр `start` в deep link ограничен 64 символами. Заполняет сам
`publish.py` при публикации.

## Карточка актуального поста на карьерном сайте (AI:stack)

Раздел AI:stack на `oleg-tsurtsumiya.ru` показывает «живую» карточку
последнего опубликованного поста канала. Данные для неё лежат в **секретном
GitHub Gist**, файл `latest.json` (id `dc74543025fd9d12733280b8e4686830`,
владелец `JohnSmith-SG`); карьерный сайт читает его по raw-URL при загрузке
страницы (CORS `*`), без перевыкладки сайта.

- `publish.py` после успешной публикации патчит gist — функция
  `update_career_card()` шлёт `PATCH https://api.github.com/gists/<id>` с
  полями `date / title / excerpt / image / link / en`.
- Токен для патча — **fine-grained PAT, права только Gists: Read and write**,
  на сервере в `/opt/content-factory/secrets/github_gist.token` (chmod 600,
  chown `cfbot:cfbot`), в git не хранится.
- Если файла токена нет — `publish.py` пишет в лог
  `gist token missing, skipping career-card update` и продолжает; сбой
  запроса тоже только логируется (`WARNING: career-card gist update failed`)
  и не роняет публикацию.
- `image` в payload указывает на картинку в ветке `main` GitHub-репозитория
  (`raw.githubusercontent.com/.../images/<basename>.jpg`) — картинка поста
  должна быть в `main` **до** публикации, иначе на карточке она не
  загрузится (карточка тогда деградирует до текстовой, это штатно).

## Сбор комментариев на самообучение

Комментарии подписчиков (прошедшие модерацию) `bot_listener.py` пишет в
`/opt/content-factory/logs/comments_for_review.jsonl` — по строке JSON на
комментарий. Сервер только собирает данные. Разбор — в живой сессии
Claude Code, см. `content-pipeline/SKILL.md`, Шаг 0.
