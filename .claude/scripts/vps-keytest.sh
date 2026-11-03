#!/usr/bin/env bash
# Проверка связи с VPS через обходной маршрут — SSH-алиас `kvmka` из
# ~/.ssh/config (ProxyJump через якорь; прямой адрес сервера с 02.11.2026
# заблокирован). Адрес, логин и ключ не печатаются — только итог.
# Запуск: bash .claude/scripts/vps-keytest.sh

VPS_ALIAS="kvmka"

if timeout 8 bash -c "exec 3<>/dev/tcp/github.com/443" 2>/dev/null; then
  echo "интернет: есть"
else
  echo "интернет: нет"
fi

OUT=$(timeout 30 ssh -o BatchMode=yes -o ConnectTimeout=10 "$VPS_ALIAS" 'echo KEY_OK' 2>&1)
if echo "$OUT" | grep -q KEY_OK; then
  echo "туннель: работает"
  echo "вход по ключу: УСПЕШНО"
elif echo "$OUT" | grep -qi "permission denied"; then
  echo "туннель: работает"
  echo "вход по ключу: сервер отказал (ключ не принят)"
else
  echo "туннель: недоступен — запусти Apps\\claude-tunnel\\start-claude-tunnel.cmd или перезагрузи ПК"
fi
exit 0
