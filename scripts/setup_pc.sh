#!/usr/bin/env bash
# Installazione completa in un solo comando (Ubuntu/WSL, Linux o macOS).
# Crea .env con password casuali (se manca), scarica OCA 18.0, crea il db lab18,
# lancia i test e stampa link e credenziali.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "ERRORE: Docker non trovato. Installa Docker Desktop e, su Windows, attiva"
  echo "Impostazioni > Resources > WSL integration > Ubuntu. Poi rilancia questo script."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERRORE: Docker non è avviato. Apri Docker Desktop, aspetta 'Engine running' e rilancia."
  exit 1
fi

# Porta 8069 occupata da qualcos'altro (es. un altro Odoo)?
if (echo > /dev/tcp/127.0.0.1/8069) >/dev/null 2>&1 && [ -z "$(docker compose ps -q odoo 2>/dev/null)" ]; then
  echo "ERRORE: la porta 8069 è già usata da un altro programma (forse un altro Odoo)."
  echo "Fermalo (es. 'docker ps' e poi 'docker stop <nome>') e rilancia questo script."
  exit 1
fi

if [ ! -f .env ]; then
  gen() { openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-16; }
  cat > .env <<ENV
POSTGRES_USER=odoo
POSTGRES_PASSWORD=$(gen)
LAB_ADMIN_PASSWORD=$(gen)
LAB_USERS_PASSWORD=$(gen)
ENV
  chmod 600 .env
  echo ">> Creato .env con password casuali."
else
  echo ">> .env già presente: uso le password esistenti."
fi

echo ">> 1/3 Scarico i moduli OCA (branch 18.0)"
./scripts/get_third_party.sh
echo ">> 2/3 Creo il database lab18 e installo i moduli (alcuni minuti)"
./scripts/init_db.sh
echo ">> 3/3 Eseguo i test automatici del flusso"
./scripts/run_tests.sh

set -a; . ./.env; set +a
cat <<MSG

=============================================================
 Odoo 18 pronto:  http://127.0.0.1:8069
 Amministratore:  admin / ${LAB_ADMIN_PASSWORD}
 Utenti di prova: commerciale, pm, analista, sviluppatore,
                  amministrazione  -> password ${LAB_USERS_PASSWORD}
 (le password sono salvate nel file .env)
=============================================================
MSG
