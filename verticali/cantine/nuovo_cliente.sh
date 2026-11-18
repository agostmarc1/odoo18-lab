#!/usr/bin/env bash
# Crea (o completa) l'Odoo 18 CE dedicato di una cantina con la Soluzione Cantina standard.
#
#   ./verticali/cantine/nuovo_cliente.sh "Cantina Bricco Rosso"            crea o completa
#   ./verticali/cantine/nuovo_cliente.sh "Cantina Bricco Rosso" --aggiorna aggiorna i moduli
#
# Cosa fa:
#  1. cartella clienti/<cliente>/ con i file da compilare (copiati dal modello, se è nuova);
#  2. file clienti/<cliente>/.env con porta e password casuali (escluso da git);
#  3. un Odoo e un database PostgreSQL SOLO per quella cantina (progetto docker "cantina_<cliente>");
#  4. azienda in Italia ed euro, contabilità italiana, pacchetto standard, dati del cliente.
# Rilanciarlo è sicuro: non reinstalla e carica solo ciò che manca.
set -euo pipefail
export MSYS_NO_PATHCONV=1        # Git Bash: non trasformare /mnt/... in percorsi Windows
cd "$(dirname "$0")"

NOME="${1:?Uso: ./nuovo_cliente.sh \"Nome della cantina\" [--aggiorna]}"
AZIONE="${2:-}"
SLUG=$(printf '%s' "$NOME" | tr '[:upper:]' '[:lower:]' \
  | sed -e 's/[àáâä]/a/g; s/[èéêë]/e/g; s/[ìíîï]/i/g; s/[òóôö]/o/g; s/[ùúûü]/u/g' \
        -e 's/^\(cantina\|azienda agricola\|tenuta\|cascina\|societa agricola\) //' \
        -e 's/[^a-z0-9]\{1,\}/_/g; s/^_//; s/_$//')
[ -n "$SLUG" ] || { echo "Nome non valido: $NOME"; exit 1; }
DIR="clienti/$SLUG"

# 1. cartella del cliente
if [ ! -d "$DIR" ]; then
  mkdir -p clienti
  cp -r addons/cantina_standard/modello_cliente "$DIR"
  RAGIONE=$(printf '%s' "$NOME" | sed 's/[\/&]/\\&/g')
  sed -i "s/__RAGIONE_SOCIALE__/$RAGIONE/" "$DIR/cliente.json"
  echo "Creata la cartella $DIR dal modello: compila cliente.json, vini.csv e clienti.csv"
  echo "e rilancia lo script per caricarli."
fi

# 2. porta e password (mai nei file versionati)
if [ ! -f "$DIR/.env" ]; then
  PORTA=8070
  for f in clienti/*/.env; do
    [ -f "$f" ] || continue
    p=$(sed -n 's/^CANTINA_PORT=//p' "$f")
    [ -n "$p" ] && [ "$p" -ge "$PORTA" ] && PORTA=$((p + 1))
  done
  pw() { openssl rand -hex 12 2>/dev/null || head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
  cat > "$DIR/.env" <<EOF
# Istanza Odoo dedicata di: $NOME  (file generato, NON va su git)
CANTINA_SLUG=$SLUG
CANTINA_DB=$SLUG
CANTINA_PORT=$PORTA
POSTGRES_PASSWORD=$(pw)
CANTINA_ADMIN_PASSWORD=$(pw)
CANTINA_USERS_PASSWORD=$(pw)
EOF
fi
set -a; . "$DIR/.env"; set +a

dc() { docker compose -p "cantina_$SLUG" --env-file "$DIR/.env" -f docker-compose.yml "$@"; }
odoo_run() { dc run --rm -T odoo odoo -d "$CANTINA_DB" --no-http --stop-after-init "$@"; }
odoo_shell() { dc run --rm -T -e CANTINA_ADMIN_PASSWORD -e CANTINA_USERS_PASSWORD odoo \
                 odoo shell -d "$CANTINA_DB" --no-http; }

dc up -d --wait db
installato=$(dc exec -T db psql -U odoo -d "$CANTINA_DB" -Atc \
  "select 1 from ir_module_module where name='cantina_standard' and state='installed'" 2>/dev/null || true)

if [ "$installato" != 1 ]; then
  dc stop odoo 2>/dev/null || true
  echo "1/4 Creo il database $CANTINA_DB (senza dati demo di Odoo) in italiano"
  odoo_run -i base --without-demo=all --load-language=it_IT
  echo "2/4 Azienda in Italia e in euro (prima della contabilità)"
  odoo_shell <<'PY'
import json
data = json.load(open('/mnt/cliente/cliente.json', encoding='utf-8'))
company = env.ref('base.main_company')
eur = env.ref('base.EUR')
eur.active = True
company.write({'name': data.get('ragione_sociale') or company.name,
               'country_id': env.ref('base.it').id, 'currency_id': eur.id})
env['res.lang']._activate_lang('it_IT')
company.partner_id.lang = 'it_IT'
env.ref('base.user_admin').write({'lang': 'it_IT', 'tz': 'Europe/Rome'})
env.cr.commit()
PY
  echo "3/4 Contabilità italiana e pacchetto Soluzione Cantina (qualche minuto...)"
  odoo_run -i l10n_it --without-demo=all
  odoo_run -i cantina_standard --without-demo=all
elif [ "$AZIONE" = "--aggiorna" ]; then
  dc stop odoo
  echo "Aggiorno i moduli della soluzione"
  odoo_run -u langhe_wine_ai,cantina_standard
fi

echo "4/4 Carico i dati della cantina da $DIR"
odoo_shell <<'PY'
import os
summary = env['cs.customer.package']._cs_load('/mnt/cliente')
Users = env['res.users'].sudo()
Users.browse(env.ref('base.user_admin').id).password = os.environ['CANTINA_ADMIN_PASSWORD']
ids = env['ir.model.data'].search([('module', '=', 'cantina_cliente'), ('model', '=', 'res.users')]).mapped('res_id')
for user in Users.browse(ids).exists():
    user.password = os.environ['CANTINA_USERS_PASSWORD']
env.cr.commit()
print(">> %(azienda)s: %(vini)s vini, %(clienti)s clienti, utenti %(utenti)s" % summary)
for item in summary['demo']:
    print(">> demo:", item)
PY
dc up -d odoo
echo
echo "Pronto: http://127.0.0.1:$CANTINA_PORT"
echo "  amministratore: admin   - password: CANTINA_ADMIN_PASSWORD in $DIR/.env"
echo "  utenti della cantina (login in cliente.json) - password: CANTINA_USERS_PASSWORD in $DIR/.env"
