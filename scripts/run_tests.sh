#!/usr/bin/env bash
# Esegue i test automatici del modulo custom (simulano il flusso end-to-end).
source "$(dirname "$0")/_lib.sh"
docker compose stop odoo
odoo_run -d "$DB" -u lab_workflow_custom --test-tags /lab_workflow_custom 2>&1 | grep -E " (ERROR|FAIL) |odoo.tests.result" || true
docker compose up -d odoo
