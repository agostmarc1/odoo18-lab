#!/usr/bin/env bash
# Aggiorna un modulo dopo modifiche al codice. Default: lab_workflow_custom
source "$(dirname "$0")/_lib.sh"
MOD=${1:-lab_workflow_custom}
docker compose stop odoo
odoo_run -d "$DB" -u "$MOD"
docker compose up -d odoo
echo "Modulo $MOD aggiornato. Ricarica la pagina nel browser."
