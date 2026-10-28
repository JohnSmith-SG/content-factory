#!/usr/bin/env bash
# Диагностика входа на VPS без вывода секрета: показывает только метаданные
# файла креденшелов (дата изменения, число строк с паролем, признаки
# лишних кавычек/пробелов). Значение пароля не печатается.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/vps.env"
f="$VPS_CRED_FILE"
echo "файл изменён: $(date -r "$f" '+%Y-%m-%d %H:%M')"
echo "строк с pass/password/pwd: $(grep -ciE '(^|[[:space:]])(pass|password|pwd)[[:space:]]*[:=]' "$f" || true)"
line="$(grep -iE '(^|[[:space:]])(pass|password|pwd)[[:space:]]*[:=]' "$f" | head -1)"
val="$(printf '%s' "$line" | sed -E 's/^[^:=]*[:=][[:space:]]*//' | tr -d '\r\n')"
case "$val" in *'"'*|*"'"*) echo "в значении есть кавычки: ДА";; *) echo "в значении есть кавычки: нет";; esac
case "$val" in *' ') echo "пробел в конце: ДА";; *) echo "пробел в конце: нет";; esac
case "$val" in *[:=]*) echo "в значении есть ':' или '=': ДА (может обрезаться разбором)";; *) echo "в значении есть ':' или '=': нет";; esac
