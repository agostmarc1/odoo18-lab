#!/usr/bin/env bash
# Scarica/aggiorna i repository OCA, SOLO branch 18.0.
set -euo pipefail
cd "$(dirname "$0")/../third-party"
BRANCH=18.0
declare -A REPOS=(
  [oca-contract]=https://github.com/OCA/contract
  [oca-project]=https://github.com/OCA/project
  [oca-web]=https://github.com/OCA/web
)
for dir in "${!REPOS[@]}"; do
  url=${REPOS[$dir]}
  if [ -d "$dir/.git" ]; then
    echo "Aggiorno $dir ($BRANCH)"
    git -C "$dir" fetch --depth 1 origin "$BRANCH" && git -C "$dir" checkout -q FETCH_HEAD
  else
    echo "Scarico $dir ($BRANCH)"
    git clone -q --depth 1 -b "$BRANCH" "$url" "$dir"
  fi
  echo "  -> $dir pronto (branch $BRANCH, commit $(git -C "$dir" rev-parse --short HEAD))"
done
