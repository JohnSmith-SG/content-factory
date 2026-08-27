#!/usr/bin/env bash
# Обёртка для доступа к VPS контент-завода (см. .claude/deploy.md).
# Пароль читается из локального файла VPN-креденшелов и передаётся в
# plink/pscp внутри процесса — он никогда не печатается в stdout/stderr,
# не попадает в историю команд и не виден в карточке вызова инструмента.
#
# Настройки (адрес сервера, путь к файлу с паролем) — в vps.env рядом с
# этим скриптом. Скопируй vps.env.example -> vps.env и впиши свои значения.
# vps.env в git не попадает.
#
# Использование:
#   vps.sh ssh '<удалённая команда>'      — выполнить команду на сервере
#   vps.sh get <remote-path> <local-path> — скачать файл с сервера
#   vps.sh put <local-path> <remote-path> — загрузить файл на сервер
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/vps.env"

[ -f "$ENV_FILE" ] || { echo "vps.sh: нет $ENV_FILE — скопируй vps.env.example и заполни" >&2; exit 1; }
# shellcheck disable=SC1090
. "$ENV_FILE"

: "${VPS_HOST:?vps.sh: VPS_HOST не задан в vps.env}"
: "${VPS_CRED_FILE:?vps.sh: VPS_CRED_FILE не задан в vps.env}"

[ -f "$VPS_CRED_FILE" ] || { echo "vps.sh: файл креденшелов не найден: $VPS_CRED_FILE" >&2; exit 1; }

# Строка с паролем: "password: xxx", "pass = xxx" и т.п.
PASS="$(grep -iE '(^|[[:space:]])(pass|password|pwd)[[:space:]]*[:=]' "$VPS_CRED_FILE" \
        | head -1 | sed -E 's/^[^:=]*[:=][[:space:]]*//' | tr -d '\r\n')"

if [ -z "$PASS" ]; then
  echo "vps.sh: не удалось разобрать пароль из $VPS_CRED_FILE" >&2
  exit 1
fi

cmd="${1:-}"
case "$cmd" in
  ssh)
    shift
    exec plink -batch -pw "$PASS" "$VPS_HOST" "$@"
    ;;
  get)
    shift
    [ $# -eq 2 ] || { echo "vps.sh get <remote-path> <local-path>" >&2; exit 2; }
    exec pscp -batch -pw "$PASS" "$VPS_HOST:$1" "$2"
    ;;
  put)
    shift
    [ $# -eq 2 ] || { echo "vps.sh put <local-path> <remote-path>" >&2; exit 2; }
    exec pscp -batch -pw "$PASS" "$1" "$VPS_HOST:$2"
    ;;
  *)
    echo "vps.sh: неизвестная команда '$cmd'. Допустимо: ssh | get | put" >&2
    exit 2
    ;;
esac
