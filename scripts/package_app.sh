#!/usr/bin/env bash
# Crea il pacchetto dell'app "Flusso Operativo Software House" da installare in un ALTRO Odoo 18 CE.
# Risultato: dist/flusso_operativo_18.0/ (cartella) e dist/flusso_operativo_18.0.zip
# Contiene la nostra app + i moduli OCA 18.0 da cui dipende (copiati senza modifiche).
set -euo pipefail
cd "$(dirname "$0")/.."

APP=lab_workflow_custom
# modulo OCA -> cartella del repo OCA in third-party/
declare -A OCA=(
  [subscription_oca]=oca-contract
  [project_timeline]=oca-project
  [web_timeline]=oca-web
)
NAME=flusso_operativo_18.0
OUT=dist/$NAME

for mod in "${!OCA[@]}"; do
  [ -d "third-party/${OCA[$mod]}/$mod" ] || { echo "Manca third-party/${OCA[$mod]}/$mod: lancia ./scripts/get_third_party.sh"; exit 1; }
done

rm -rf "$OUT" "dist/$NAME.zip"
mkdir -p "$OUT"
cp -r "addons/$APP" "$OUT/"
for mod in "${!OCA[@]}"; do
  cp -r "third-party/${OCA[$mod]}/$mod" "$OUT/"
done
find "$OUT" -name '__pycache__' -type d -prune -exec rm -rf {} +

{
  echo "Pacchetto: app Flusso Operativo Software House per Odoo 18.0 Community"
  echo "Creato il: $(date '+%Y-%m-%d %H:%M')"
  echo
  echo "Contenuto (una cartella per modulo):"
  echo "  $APP  <- la nostra app (versione $(grep -o '"version": *"[^"]*"' "addons/$APP/__manifest__.py" | cut -d'"' -f4))"
  for mod in "${!OCA[@]}"; do
    echo "  $mod  <- OCA ${OCA[$mod]}, branch 18.0, commit $(git -C "third-party/${OCA[$mod]}" rev-parse --short HEAD)"
  done
  cat <<'TXT'

Come installarla in un altro Odoo 18.0 Community:
  1. Copia TUTTE le cartelle di questo pacchetto in una cartella di moduli del server
     (una cartella elencata in addons_path del file di configurazione di Odoo).
  2. Riavvia Odoo.
  3. Accedi come amministratore, attiva la modalità sviluppatore e vai in
     Applicazioni > Aggiorna elenco applicazioni.
  4. Cerca "Flusso Operativo Software House" e premi Installa.
     Odoo installa da solo anche CRM, Vendite, Progetto, Fogli ore, Fatturazione e i moduli OCA.

Video e documentazione (dentro l'app, cartella lab_workflow_custom/static/description/):
  - Nella scheda dell'app (Applicazioni > Flusso Operativo Software House) ci sono la guida
    passo-passo, il video dimostrativo con i capitoli e il link all'analisi tecnica.
  - Si aprono anche direttamente, a Odoo avviato:
      <indirizzo Odoo>/lab_workflow_custom/static/description/video.html
      <indirizzo Odoo>/lab_workflow_custom/static/description/analisi_tecnica.html
  - Il video da solo: lab_workflow_custom/static/description/demo_flusso_operativo.mp4

Note:
  - Funziona solo su Odoo 18.0 Community (non su altre versioni).
  - Gli utenti di prova (Giuseppe Commerciale, Marco Project Manager, ...) si creano SOLO se il database
    ha i dati demo. In un database "vero" assegna i ruoli agli utenti da
    Impostazioni > Utenti (sezione "Ruoli Flusso Operativo").
  - I moduli OCA sono distribuiti con licenza AGPL-3, la nostra app con LGPL-3.
TXT
} > "$OUT/LEGGIMI.txt"

# ZIP con percorsi "/" (leggibile anche su server Linux). Compress-Archive di Windows PowerShell 5.1
# scrive "\" nei percorsi: resta solo come ultima scelta.
PY=""
for c in python3 python py; do   # su Windows "python3" può essere solo l'alias del Microsoft Store
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import zipfile" >/dev/null 2>&1; then PY=$c; break; fi
done
if command -v zip >/dev/null 2>&1; then
  (cd dist && zip -qr "$NAME.zip" "$NAME")
elif [ -n "$PY" ] && (cd dist && "$PY" -m zipfile -c "$NAME.zip" "$NAME"); then
  :
elif command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -Command "Compress-Archive -Path 'dist/$NAME' -DestinationPath 'dist/$NAME.zip' -Force"
fi

echo "Pacchetto pronto:"
echo "  cartella: $OUT"
[ -f "dist/$NAME.zip" ] && echo "  zip:      dist/$NAME.zip"
