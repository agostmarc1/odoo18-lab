#!/usr/bin/env bash
# Prova che il pacchetto si installi da solo su un Odoo 18 CE "pulito":
#  - immagine ufficiale odoo:18.0 (senza le aggiunte del laboratorio)
#  - nei moduli aggiuntivi SOLO il contenuto di dist/flusso_operativo_18.0.zip
#  - database nuovo e vuoto, solo inglese; prima senza e poi con i dati di esempio
# Poi esegue i test dell'app e cancella i database di prova.
# Uso: ./scripts/prova_installazione_pulita.sh   (il laboratorio deve essere avviato)
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/package_app.sh > /dev/null
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
unzip -q dist/flusso_operativo_18.0.zip -d "$WORK/pkg"

# credenziali del database: le stesse del container del laboratorio (non scritte su file versionati)
C=$(docker compose ps -q odoo)
[ -n "$C" ] || { echo "Il laboratorio non è avviato: docker compose up -d"; exit 1; }
docker inspect "$C" --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(HOST|USER|PASSWORD)=' > "$WORK/cred.env"
NET=$(docker inspect "$C" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}')
W=$(cd "$WORK" && pwd -W 2>/dev/null || pwd)

odoo_pulito() {
  MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" --env-file "$W/cred.env" \
    -v "$W/pkg:/mnt/pkg:ro" odoo:18.0 odoo \
    --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/pkg/flusso_operativo_18.0 \
    --stop-after-init --no-http "$@"
}
elimina_db() { docker compose exec -T db sh -c "dropdb -U \"\$POSTGRES_USER\" --if-exists $1"; }

esito=0
for prova in senza_demo con_demo; do
  DB=prova_pulita_$prova
  elimina_db "$DB"
  [ $prova = senza_demo ] && DEMO=(--without-demo=all) || DEMO=()
  echo "== Installazione su Odoo pulito ($prova)"
  if ! odoo_pulito -d "$DB" -i lab_workflow_custom "${DEMO[@]}" > "$WORK/$prova.log" 2>&1 \
      || grep -qE " (ERROR|CRITICAL) " "$WORK/$prova.log"; then
    echo "   NON RIUSCITA:"; grep -E " (ERROR|CRITICAL) |Error" "$WORK/$prova.log" | tail -5; esito=1
  else
    grep -o "[0-9]* modules loaded" "$WORK/$prova.log" | tail -1 | sed 's/^/   ok, /'
    echo "== Test dell'app ($prova)"
    odoo_pulito -d "$DB" -u lab_workflow_custom --test-tags /lab_workflow_custom \
      > "$WORK/$prova.test.log" 2>&1 || true
    if ! grep -qE " 0 failed, 0 error\(s\) of [1-9][0-9]* tests" "$WORK/$prova.test.log"; then
      echo "   TEST NON RIUSCITI:"; grep -E "ERROR: |FAIL: |of [0-9]+ tests" "$WORK/$prova.test.log" | tail -8; esito=1
    else
      echo "   ok, test passati"
    fi
  fi
  elimina_db "$DB"
done
[ $esito = 0 ] && echo "Pacchetto installabile su Odoo 18 CE pulito." || echo "Ci sono problemi: vedi sopra."
exit $esito
