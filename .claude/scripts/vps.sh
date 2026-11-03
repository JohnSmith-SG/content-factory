#!/usr/bin/env bash
# Обёртка для доступа к VPS контент-завода (см. .claude/deploy.md).
# С 02.11.2026 прямой адрес сервера заблокирован — ходим через SSH-алиас
# `kvmka` из ~/.ssh/config (ProxyJump через якорь, вход только по ключу
# ~/.ssh/id_ed25519). Паролей здесь нет: на сервере вход по паролю отключён.
# Адрес, логин и ключ живут только в ~/.ssh/config, сюда не дублируются.
#
# Использование:
#   vps.sh ssh '<удалённая команда>'      — выполнить команду на сервере
#   vps.sh get <remote-path> <local-path> — скачать файл с сервера
#   vps.sh put <local-path> <remote-path> — загрузить файл на сервер
set -euo pipefail

VPS_ALIAS="kvmka"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)

cmd="${1:-}"
case "$cmd" in
  ssh)
    shift
    exec ssh "${SSH_OPTS[@]}" "$VPS_ALIAS" "$@"
    ;;
  get)
    shift
    [ $# -eq 2 ] || { echo "vps.sh get <remote-path> <local-path>" >&2; exit 2; }
    exec scp "${SSH_OPTS[@]}" "$VPS_ALIAS:$1" "$2"
    ;;
  put)
    shift
    [ $# -eq 2 ] || { echo "vps.sh put <local-path> <remote-path>" >&2; exit 2; }
    exec scp "${SSH_OPTS[@]}" "$1" "$VPS_ALIAS:$2"
    ;;
  *)
    echo "vps.sh: неизвестная команда '$cmd'. Допустимо: ssh | get | put" >&2
    exit 2
    ;;
esac
