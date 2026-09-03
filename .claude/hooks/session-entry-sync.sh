#!/usr/bin/env bash
# SessionStart-хук content-factory.
# Механическая часть входа в проект (см. content-pipeline, Шаги 0-1.5):
#   1. git pull --ff-only
#   2. свериться с sent/ на сервере -> проставить published в локальных posts/*.json
#   3. если что-то изменилось: commit + push (без вопросов)
#   4. скачать свежий лог комментариев
#   5. напечатать короткую сводку — она уходит в контекст Claude
# Содержательные шаги (разбор комментариев, генерация постов при нехватке
# резерва, ревью, превью) хук НЕ делает — их выполняет Claude по скиллу.
# Хук всегда завершается с кодом 0 — не должен ломать старт сессии.

set -uo pipefail
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 0
VPS="$REPO/.claude/scripts/vps.sh"

log() { printf '%s\n' "$*"; }

log "=== content-factory: синхронизация при входе ==="

# --- 1. подтянуть main ---
git pull --ff-only origin main --quiet 2>/dev/null \
  && log "git: main обновлён (ff-only)" \
  || log "git: pull пропущен (нет сети или расхождение веток)"

SENT_LIST=""
QUEUE_COUNT="?"
if [ -x "$VPS" ] || [ -f "$VPS" ]; then
  SRV="$(bash "$VPS" ssh "ls -1 /opt/content-factory/sent/*.json 2>/dev/null | xargs -n1 basename 2>/dev/null; echo '---'; ls -1 /opt/content-factory/queue/*.json 2>/dev/null | wc -l" 2>/dev/null)"
  if [ -n "$SRV" ]; then
    SENT_LIST="$(printf '%s\n' "$SRV" | sed '/^---$/,$d')"
    QUEUE_COUNT="$(printf '%s\n' "$SRV" | sed '1,/^---$/d' | tr -d '[:space:]')"
    log "сервер: в sent/ $(printf '%s\n' "$SENT_LIST" | grep -c . ) шт., в queue/ ${QUEUE_COUNT} шт."
    # свежий лог комментариев
    bash "$VPS" get /opt/content-factory/logs/comments_for_review.jsonl "$REPO/tmp/comments_for_review.jsonl" >/dev/null 2>&1 \
      && log "комментарии: лог скачан в tmp/" \
      || log "комментарии: скачать не удалось"
  else
    log "сервер: недоступен — сверка sent/ и комментариев пропущена"
  fi
else
  log "сервер: обёртка vps.sh не настроена — серверная часть пропущена"
fi

# --- 2/3. проставить published и закоммитить ---
CHANGED="$(SENT_LIST="$SENT_LIST" python - "$REPO" <<'PY'
import json, os, sys, glob
repo = sys.argv[1]
sent = set(l.strip() for l in os.environ.get("SENT_LIST","").splitlines() if l.strip())
changed = []
for path in glob.glob(os.path.join(repo, "posts", "*.json")):
    name = os.path.basename(path)
    if name not in sent:
        continue
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        continue
    if data.get("status") == "published":
        continue
    data["status"] = "published"
    m = name[:10]
    if len(m) == 10 and m[4] == "-" and m[7] == "-":
        data.setdefault("published_at", m)
        data["published_at"] = m
    # сохранить порядок ключей насколько можно: status/published_at в начало
    ordered = {}
    for k in ("schema_version", "status", "published_at"):
        if k in data:
            ordered[k] = data.pop(k)
    ordered.update(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
        f.write("\n")
    changed.append(name)
print("\n".join(changed))
PY
)"

if [ -n "$CHANGED" ]; then
  log "статус: отмечены published по данным сервера:"
  printf '  - %s\n' $CHANGED
  git add posts/ 2>/dev/null
  if git commit -m "sync: отметить published по данным сервера [auto-хук]" --quiet 2>/dev/null; then
    for i in 1 2 3; do
      git push origin main --quiet 2>/dev/null && { log "git: изменения запушены"; break; }
      [ "$i" = 3 ] && log "git: push не удался — запушить вручную позже"
      sleep 2
    done
  fi
else
  log "статус: локальные posts/ уже совпадают с сервером"
fi

# --- 4. сводка по очереди и комментариям ---
python - "$REPO" "$QUEUE_COUNT" <<'PY'
import json, os, sys, glob, datetime
repo, qcount = sys.argv[1], sys.argv[2]
now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
today = now.date()
print(f"сейчас по Москве: {now:%Y-%m-%d %H:%M} ({['пн','вт','ср','чт','пт','сб','вс'][today.weekday()]})")

approved_future = []
missed = []
for path in sorted(glob.glob(os.path.join(repo, "posts", "*.json"))):
    name = os.path.basename(path)
    m = name[:10]
    try:
        d = datetime.date.fromisoformat(m)
    except ValueError:
        continue
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f).get("status")
    except Exception:
        continue
    if st != "published" and d <= today and d.weekday() < 5:
        missed.append(name)
    if st == "approved" and d > today and d.weekday() < 5:
        approved_future.append(name)

print(f"резерв (approved, будущие будни): {len(approved_future)} / норма 5")
if len(approved_future) < 5:
    print(f"  !! НЕ ХВАТАЕТ {5 - len(approved_future)} — нужен new-post")
if missed:
    print("  !! пропущенные/наступившие слоты:", ", ".join(missed))
print(f"очередь на сервере (queue/): {qcount}")

# новые комментарии
clog = os.path.join(repo, "tmp", "comments_for_review.jsonl")
review = os.path.join(repo, ".claude", "last-comment-review.json")
last = ""
if os.path.exists(review):
    try:
        last = json.load(open(review, encoding="utf-8")).get("last_reviewed_at", "")
    except Exception:
        pass
new = 0
if os.path.exists(clog):
    for line in open(clog, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            ts = json.loads(line).get("logged_at", "")
        except Exception:
            continue
        if not last or ts > last:
            new += 1
print(f"новых комментариев с прошлой проверки: {new}" + ("  !! разобрать (Шаг 0)" if new else ""))

# погасить глобальное ежедневное напоминание на сегодня — пользователь уже
# в проекте (см. ~/.claude/hooks/cf-daily-trigger.sh). Назавтра проверка
# посчитает заново.
_cd = os.path.expanduser("~/.claude")
try:
    with open(os.path.join(_cd, ".cf-daily-stamp"), "w") as _f:
        _f.write(today.isoformat())
    for _n in (".cf-daily-pending", ".cf-daily-status"):
        _p = os.path.join(_cd, _n)
        if os.path.exists(_p):
            os.remove(_p)
except Exception:
    pass
PY

log "=== конец синхронизации; дальше — по скиллу content-pipeline ==="
exit 0
