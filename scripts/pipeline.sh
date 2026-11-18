#!/usr/bin/env bash
# Pipeline di rilascio: esegue IN ORDINE tutte le fasi necessarie dopo una modifica al codice e si
# ferma al primo errore, dicendo da quale fase ripartire.
#
#   ./scripts/pipeline.sh                      fasi 1-8 (tutto tranne video e salvataggio su git)
#   ./scripts/pipeline.sh --video              anche la fase 9 (video utente e tecnico, ~30 minuti)
#   ./scripts/pipeline.sh --commit "messaggio" anche la fase 10 (commit su un ramo nuovo, senza push)
#   ./scripts/pipeline.sh --da 4               riparte dalla fase 4
#   ./scripts/pipeline.sh --solo 6             esegue solo la fase 6
#   ./scripts/pipeline.sh --elenco             mostra le fasi senza eseguire nulla
#
# Fasi che RIAVVIANO Odoo (lanciare la pipeline vale come conferma):
#   4 (laboratorio, circa un minuto), 6 (istanze delle cantine, una alla volta).
# Il registro completo di ogni esecuzione va in backups/pipeline_<data>.log (escluso da git).
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

FASI=(
  "Controlli iniziali: Docker, file .env, laboratorio avviato"
  "Prova su Odoo pulito della Soluzione Cantina (verticali/cantine/prova_pacchetto.sh)"
  "Prova su Odoo pulito dell'app del laboratorio (scripts/prova_installazione_pulita.sh)"
  "Copia di sicurezza di lab18, poi aggiornamento dell'app (riavvio di Odoo 8069)"
  "Dati di esempio nuovi in lab18 e test dell'app sul database vero"
  "Aggiornamento delle istanze delle cantine (riavvio di ciascuna, porte 8070+)"
  "Verifica finale: accesso web a laboratorio e cantine, dati presenti"
  "Pacchetto ZIP dell'app per altri Odoo (scripts/package_app.sh)"
  "Video utente e tecnico (solo con --video)"
  "Salvataggio su git in un ramo nuovo (solo con --commit \"messaggio\")"
)

DA=1; SOLO=""; VIDEO=0; COMMIT_MSG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --da) DA="$2"; shift 2 ;;
    --solo) SOLO="$2"; shift 2 ;;
    --video) VIDEO=1; shift ;;
    --commit) COMMIT_MSG="${2:?scrivi il messaggio del commit tra virgolette}"; shift 2 ;;
    --elenco) for i in "${!FASI[@]}"; do echo "$((i + 1)). ${FASI[$i]}"; done; exit 0 ;;
    *) echo "Opzione sconosciuta: $1 (vedi l'intestazione di scripts/pipeline.sh)"; exit 1 ;;
  esac
done

mkdir -p backups
LOG="backups/pipeline_$(date +%Y%m%d_%H%M).log"
FASE=0
trap 'echo; echo "✖ Fase $FASE non riuscita: ${FASI[$((FASE - 1))]:-}"; echo "  Dettagli in $LOG"; echo "  Dopo la correzione: ./scripts/pipeline.sh --da $FASE"' ERR

da_fare() {  # $1 = numero fase
  if [ -n "$SOLO" ]; then [ "$1" = "$SOLO" ]; else [ "$1" -ge "$DA" ]; fi
}
inizio() { FASE=$1; echo; echo "━━ $1/${#FASI[@]} ${FASI[$(($1 - 1))]}"; echo "== fase $1 $(date +%T)" >> "$LOG"; }
ok() { echo "   ✔ $*"; }
esegui() { "$@" >> "$LOG" 2>&1; }      # comando con output solo nel registro
test_ok() { grep -qE " 0 failed, 0 error\(s\) of [1-9][0-9]* tests" "$1"; }

# credenziali del laboratorio (solo in memoria, mai stampate)
set -a; . ./.env; set +a

if da_fare 1; then inizio 1
  docker info > /dev/null 2>&1 || { echo "   Docker non è avviato: apri Docker Desktop e riprova."; false; }
  [ -f .env ] || { echo "   Manca .env (copia .env.example)."; false; }
  esegui docker compose up -d --wait db
  esegui docker compose up -d odoo
  ok "Docker attivo, database e Odoo del laboratorio avviati"
  for f in verticali/cantine/clienti/*/.env; do [ -f "$f" ] && ok "istanza cantina: $(sed -n 's/^CANTINA_SLUG=//p' "$f") (porta $(sed -n 's/^CANTINA_PORT=//p' "$f"))"; done
fi

if da_fare 2; then inizio 2
  ./verticali/cantine/prova_pacchetto.sh 2>&1 | tee -a "$LOG" | sed 's/^/   /'
  [ "${PIPESTATUS[0]}" = 0 ] || false
fi

if da_fare 3; then inizio 3
  ./scripts/prova_installazione_pulita.sh 2>&1 | grep -v "^NOTICE" | tee -a "$LOG" | sed 's/^/   /'
  [ "${PIPESTATUS[0]}" = 0 ] || false
fi

if da_fare 4; then inizio 4
  DUMP="backups/lab18_prima_pipeline_$(date +%Y%m%d_%H%M).dump"
  docker compose exec -T db pg_dump -U "$POSTGRES_USER" -Fc lab18 > "$DUMP"
  ok "copia di sicurezza: $DUMP ($(du -h "$DUMP" | cut -f1)); per tornare indietro: pg_restore"
  esegui docker compose stop odoo
  esegui docker compose run --rm -T odoo odoo -d lab18 -u lab_workflow_custom --no-http --stop-after-init
  if grep -qE " (CRITICAL|ERROR) " <(sed -n "/== fase 4/,\$p" "$LOG"); then
    docker compose up -d odoo > /dev/null 2>&1; echo "   errori durante l'aggiornamento"; false
  fi
  esegui docker compose up -d odoo
  ok "app aggiornata alla versione $(grep -o '"version": *"[^"]*"' addons/lab_workflow_custom/__manifest__.py | cut -d'"' -f4), Odoo riavviato"
fi

if da_fare 5; then inizio 5
  esegui ./scripts/load_synthetic.sh   # aggiunge solo ciò che manca e reimposta le password di prova
  ok "dati di esempio completati (aggiunge solo ciò che manca)"
  TLOG=backups/pipeline_test_lab18.log
  # i test girano in una transazione annullata alla fine: il database non cambia
  esegui docker compose stop odoo
  docker compose run --rm -T odoo odoo -d lab18 -u lab_workflow_custom --test-tags /lab_workflow_custom \
    --no-http --stop-after-init > "$TLOG" 2>&1 || true
  esegui docker compose up -d odoo
  test_ok "$TLOG" || { grep -E "FAIL:|ERROR: |of [0-9]+ tests" "$TLOG" | tail -8 | sed 's/^/   /'; false; }
  ok "test dell'app su lab18: $(grep -oE 'of [0-9]+ tests' "$TLOG" | tail -1 | sed 's/of //') passati"
fi

if da_fare 6; then inizio 6
  trovate=0
  for f in verticali/cantine/clienti/*/.env; do
    [ -f "$f" ] || continue
    slug=$(sed -n 's/^CANTINA_SLUG=//p' "$f")
    [ "$slug" = "_prova" ] && continue
    nome=$(sed -n 's/^# Istanza Odoo dedicata di: \(.*\)  (file.*/\1/p' "$f")
    trovate=$((trovate + 1))
    esegui ./verticali/cantine/nuovo_cliente.sh "${nome:-$slug}" --aggiorna
    ok "$slug aggiornata e riavviata"
  done
  [ $trovate -gt 0 ] || ok "nessuna istanza di cantina da aggiornare"
fi

if da_fare 7; then inizio 7
  python - "$LAB_ADMIN_PASSWORD" >> "$LOG" 2>&1 <<'PY' || { echo "   accesso al laboratorio non riuscito"; false; }
import json, sys, urllib.request
req = urllib.request.Request("http://127.0.0.1:8069/web/session/authenticate", headers={"Content-Type": "application/json"},
    data=json.dumps({"jsonrpc": "2.0", "params": {"db": "lab18", "login": "admin", "password": sys.argv[1]}}).encode())
for _ in range(30):
    try:
        uid = json.load(urllib.request.urlopen(req, timeout=20)).get("result", {}).get("uid"); break
    except Exception:
        import time; time.sleep(4)
else:
    uid = None
print("lab18 uid", uid); sys.exit(0 if uid else 1)
PY
  ok "laboratorio http://127.0.0.1:8069: accesso admin riuscito"
  for f in verticali/cantine/clienti/*/.env; do
    [ -f "$f" ] || continue
    ( set -a; . "$f"; set +a; [ "$CANTINA_SLUG" = "_prova" ] && exit 0
      python - >> "$LOG" 2>&1 <<'PY'
import json, os, sys, time, urllib.request
base = "http://127.0.0.1:%s" % os.environ["CANTINA_PORT"]
req = urllib.request.Request(base + "/web/session/authenticate", headers={"Content-Type": "application/json"},
    data=json.dumps({"jsonrpc": "2.0", "params": {"db": os.environ["CANTINA_DB"], "login": "admin",
                     "password": os.environ["CANTINA_ADMIN_PASSWORD"]}}).encode())
for _ in range(30):
    try:
        uid = json.load(urllib.request.urlopen(req, timeout=20)).get("result", {}).get("uid"); break
    except Exception:
        time.sleep(4)
else:
    uid = None
print(os.environ["CANTINA_SLUG"], "uid", uid); sys.exit(0 if uid else 1)
PY
    ) || { echo "   accesso all'istanza $(sed -n 's/^CANTINA_SLUG=//p' "$f") non riuscito"; false; }
    ok "cantina $(sed -n 's/^CANTINA_SLUG=//p' "$f") http://127.0.0.1:$(sed -n 's/^CANTINA_PORT=//p' "$f"): accesso admin riuscito"
  done
  docker compose run --rm -T odoo odoo shell -d lab18 --no-http 2>> "$LOG" <<'PY' | grep "^>>" | sed 's/^>> /   ✔ /'
v = env.ref('lab_workflow_custom.synth_vertical_cantina', raise_if_not_found=False)
if v:
    print(">> %s: %d installazioni, %d trattative, ore %d → %d" % (v.name, v.install_count, v.pipeline_count, v.pilot_hours, v.standard_hours))
else:
    print(">> soluzione di settore non presente (database senza scenario sintetico)")
PY
  true
fi

if da_fare 8; then inizio 8
  esegui ./scripts/package_app.sh
  ok "pacchetto: dist/flusso_operativo_18.0.zip"
fi

if da_fare 9; then inizio 9
  if [ $VIDEO = 1 ]; then
    esegui ./scripts/registra_video.sh && ok "video per l'utente rigenerato"
    esegui ./scripts/registra_video.sh --tecnico && ok "video tecnico rigenerato"
  else
    echo "   saltata (aggiungi --video per rigenerare i video)"
  fi
fi

if da_fare 10; then inizio 10
  if [ -n "$COMMIT_MSG" ]; then
    RAMO="rilascio-$(grep -o '"version": *"[^"]*"' addons/lab_workflow_custom/__manifest__.py | cut -d'"' -f4)"
    git checkout -b "$RAMO" >> "$LOG" 2>&1 || git checkout "$RAMO" >> "$LOG" 2>&1
    git add -A
    if git diff --cached --name-only | grep -E '(^|/)\.env$'; then echo "   un file .env sta per essere salvato: fermo tutto"; git reset -q; false; fi
    git commit -q -m "$COMMIT_MSG" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    ok "commit $(git rev-parse --short HEAD) sul ramo $RAMO (nessun push)"
  else
    echo "   saltata (aggiungi --commit \"messaggio\" per salvare su git)"
  fi
fi

echo; echo "Pipeline completata. Registro: $LOG"
