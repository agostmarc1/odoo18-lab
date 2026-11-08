# Moduli di terze parti (OCA)

Questa cartella NON è versionata (tranne questo file). Si riempie con:

    ./scripts/get_third_party.sh

Scarica SOLO il branch `18.0` dei repository OCA:
- `oca-contract` -> https://github.com/OCA/contract (usiamo `subscription_oca` per il canone AMS)
- `oca-project`  -> https://github.com/OCA/project  (usiamo `project_timeline`)
- `oca-web`      -> https://github.com/OCA/web      (usiamo `web_timeline`, richiesto da `project_timeline`)

Per aggiungere un repo: aggiungilo in `scripts/get_third_party.sh` e in `addons_path` di `config/odoo.conf`.
