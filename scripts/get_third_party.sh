#!/usr/bin/env bash
# Scarica/aggiorna i repository OCA, SOLO branch 18.0.
set -euo pipefail
cd "$(dirname "$0")/../third-party"
BRANCH=18.0
declare -A REPOS=(
  [oca-contract]=https://github.com/OCA/contract
  [oca-project]=https://github.com/OCA/project
  [oca-web]=https://github.com/OCA/web
  # ticketing (helpdesk_mgmt e moduli collegati)
  [oca-helpdesk]=https://github.com/OCA/helpdesk
  # localizzazione italiana (l10n-italy) e repo OCA da cui dipende
  [oca-l10n-italy]=https://github.com/OCA/l10n-italy
  [oca-account-closing]=https://github.com/OCA/account-closing
  [oca-account-financial-reporting]=https://github.com/OCA/account-financial-reporting
  [oca-account-financial-tools]=https://github.com/OCA/account-financial-tools
  [oca-account-payment]=https://github.com/OCA/account-payment
  [oca-currency]=https://github.com/OCA/currency
  [oca-delivery-carrier]=https://github.com/OCA/delivery-carrier
  [oca-partner-contact]=https://github.com/OCA/partner-contact
  [oca-product-attribute]=https://github.com/OCA/product-attribute
  [oca-reporting-engine]=https://github.com/OCA/reporting-engine
  [oca-server-ux]=https://github.com/OCA/server-ux
  [oca-stock-logistics-workflow]=https://github.com/OCA/stock-logistics-workflow
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
