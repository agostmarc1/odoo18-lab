#!/usr/bin/env bash
# Scarica i repository OCA (branch 18.0) alle versioni FISSATE in scripts/oca_versions.txt:
# ogni installazione usa esattamente lo stesso codice, già provato con i test.
#   ./scripts/get_third_party.sh            -> scarica le versioni fissate
#   ./scripts/get_third_party.sh --aggiorna -> passa alle ultime del branch 18.0 e riscrive il file
#                                              (poi: test, prova_installazione_pulita.sh, commit)
set -euo pipefail
cd "$(dirname "$0")/.."
LIST=scripts/oca_versions.txt
BRANCH=18.0
MODE=${1:-}
[ -z "$MODE" ] || [ "$MODE" = --aggiorna ] || { echo "Uso: $0 [--aggiorna]"; exit 1; }

NEW=$(mktemp)
grep '^#' "$LIST" > "$NEW"
while read -r dir url commit; do
  case "$dir" in ''|'#'*) continue ;; esac
  path=third-party/$dir
  [ -d "$path/.git" ] || { git init -q "$path"; git -C "$path" remote add origin "$url"; }
  if [ "$MODE" = --aggiorna ]; then
    git -C "$path" fetch -q --depth 1 origin "$BRANCH"
  else
    git -C "$path" fetch -q --depth 1 origin "$commit"
  fi
  git -C "$path" checkout -q FETCH_HEAD
  got=$(git -C "$path" rev-parse HEAD)
  if [ "$MODE" != --aggiorna ] && [ "$got" != "$commit" ]; then
    echo "ERRORE: $dir è al commit $got invece di $commit"; exit 1
  fi
  echo "  $dir pronto (commit ${got:0:10})"
  echo "$dir $url $got" >> "$NEW"
done < "$LIST"

if [ "$MODE" = --aggiorna ]; then
  mv "$NEW" "$LIST"; echo "Versioni aggiornate in $LIST: ora test e prova_installazione_pulita.sh."
else
  rm -f "$NEW"
fi
