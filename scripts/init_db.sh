#!/usr/bin/env bash
# Crea il database lab18 (Italia, euro, lingua italiana) con la localizzazione italiana OCA e la
# nostra app. Niente dati demo standard di Odoo: solo lo scenario sintetico della software house
# (load_synthetic_data), cosi' nel gestionale si vedono solo dati che verificano il nostro flusso.
source "$(dirname "$0")/_lib.sh"
docker compose up -d --wait db
# Già installato? (un db vuoto creato da Odoo all'avvio NON conta come installato)
if docker compose exec -T db psql -U "$POSTGRES_USER" -d "$DB" -Atc \
     "select 1 from ir_module_module where name='lab_workflow_custom' and state='installed'" \
     2>/dev/null | grep -q 1; then
  echo "Il database $DB è già installato: non reinstallo nulla (per ripartire da zero: ./scripts/reset_db.sh)."
  docker compose up -d odoo
  exit 0
fi
docker compose stop odoo || true
echo "1/5 Creo $DB (senza dati demo di Odoo) con la lingua italiana"
odoo_run -d "$DB" -i base --without-demo=all --load-language=it_IT
echo "2/5 Imposto l'azienda in Italia e in euro (prima della contabilità)"
setup_company_italy
echo "3/5 Installo la contabilità italiana (piano dei conti e IVA)"
# va fatta da sola: alcuni moduli OCA (es. Intrastat) nei dati demo usano le imposte italiane
odoo_run -d "$DB" -i l10n_it --without-demo=all
echo "4/5 Installo localizzazione italiana OCA e app (10-20 minuti la prima volta...)"
odoo_run -d "$DB" -i "$MODULES,$ITALY_MODULES" --without-demo=all
finalize_companies
echo "5/5 Carico i dati sintetici della software house"
load_synthetic_data
set_passwords
docker compose up -d odoo
echo "Fatto. Apri http://127.0.0.1:8069  (utente: admin, password: LAB_ADMIN_PASSWORD in .env)"
