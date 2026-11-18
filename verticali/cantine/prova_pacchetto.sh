#!/usr/bin/env bash
# Prova che la Soluzione Cantina si installi da sola su un Odoo 18 CE pulito:
# immagine ufficiale odoo:18.0, database nuovo solo in inglese, prima senza e poi con i dati
# di esempio di Odoo, e test dei due moduli. Usa un'istanza usa-e-getta (progetto docker
# "cantina_prova") che alla fine viene cancellata: le istanze dei clienti non si toccano.
# Uso: ./verticali/cantine/prova_pacchetto.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"

WORK=clienti/_prova            # file temporanei qui dentro (esclusa da git): Docker la vede anche su Windows
rm -rf "$WORK"; mkdir -p "$WORK"
cat > "$WORK/prova.env" <<ENV
CANTINA_SLUG=_prova
CANTINA_DB=prova
CANTINA_PORT=8099
POSTGRES_PASSWORD=$(openssl rand -hex 12 2>/dev/null || echo prova$RANDOM$RANDOM)
ENV
dc() { docker compose -p cantina_prova --env-file "$WORK/prova.env" -f docker-compose.yml "$@"; }
pulizia() { dc down -v --remove-orphans > /dev/null 2>&1 || true; rm -rf "$WORK"; }
trap pulizia EXIT
dc up -d --wait db > "$WORK/db.log" 2>&1 || { cat "$WORK/db.log"; exit 1; }

esito=0
for prova in senza_demo con_demo; do
  DB=prova_$prova
  [ $prova = senza_demo ] && DEMO=(--without-demo=all) || DEMO=()
  echo "== Installazione su Odoo pulito ($prova)"
  if ! dc run --rm -T odoo odoo -d "$DB" -i cantina_standard "${DEMO[@]}" --no-http --stop-after-init \
        > "$WORK/$prova.log" 2>&1 || grep -qE " (ERROR|CRITICAL) " "$WORK/$prova.log"; then
    echo "   NON RIUSCITA:"; grep -E " (ERROR|CRITICAL) |Error" "$WORK/$prova.log" | tail -8; esito=1; continue
  fi
  grep -o "[0-9]* modules loaded" "$WORK/$prova.log" | tail -1 | sed 's/^/   ok, /'
  echo "== Test dei moduli ($prova)"
  dc run --rm -T odoo odoo -d "$DB" -u langhe_wine_ai,cantina_standard --no-http --stop-after-init \
     --test-tags /langhe_wine_ai,/cantina_standard > "$WORK/$prova.test.log" 2>&1 || true
  if grep -qE " 0 failed, 0 error\(s\) of [1-9][0-9]* tests" "$WORK/$prova.test.log"; then
    grep -oE "of [0-9]+ tests" "$WORK/$prova.test.log" | tail -1 | sed 's/^/   ok, test passati: /'
  else
    echo "   TEST NON RIUSCITI:"; grep -E "ERROR: |FAIL: |Traceback|Error:|of [0-9]+ tests" "$WORK/$prova.test.log" | tail -15
    cp "$WORK/$prova.test.log" "cantina_$prova.test.log.txt"   # resta per l'analisi (escluso da git)
    esito=1
  fi
done
[ $esito = 0 ] && echo "Soluzione Cantina installabile su Odoo 18 CE pulito." || echo "Ci sono problemi: vedi sopra."
exit $esito
