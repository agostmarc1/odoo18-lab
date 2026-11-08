# CLAUDE.md – istruzioni per le sessioni di vibe coding

## Chi è l'utente
Marco non è uno sviluppatore e lavora solo parlando con Claude, senza editor.
- Spiega **sempre** ogni modifica in parole semplici, in 2-3 righe, prima e dopo averla fatta.
- Per ogni funzionalità toccata indica gli **owner del processo** coinvolti: Commerciale, Project Manager,
  Analista Funzionale/Sviluppatore, Amministrazione.
- Se qualcosa fallisce, spiega cosa è successo prima di riprovare con un'altra strada.
- Chiedi conferma prima di installare software, usare permessi di amministratore o fare riavvii.
- Lavora solo dentro questa cartella.

## Versione e stack
- **Odoo 18.0 Community Edition**, immagine Docker `odoo:18.0` (mai `latest`), PostgreSQL 16.
- Database unico: `lab18` (con dati demo). Odoo è su http://127.0.0.1:8069.
- Dev mode: `--dev=xml,reload` nel `command` di `docker-compose.yml`. Odoo 18 **non** legge `dev_mode` da `odoo.conf`.
- Credenziali solo in `.env` (gitignored). **Mai password o token in file versionati.** Gli utenti demo
  non hanno password nell'XML: le imposta `scripts/init_db.sh` leggendole da `.env`.

## Struttura
```
docker-compose.yml   config/odoo.conf   .env(.example)
addons/lab_workflow_custom/   <- moduli custom (mount /mnt/extra-addons)
third-party/oca-*            <- repo OCA branch 18.0 (mount /mnt/third-party, gitignored)
scripts/                     <- setup_pc, init_db, reset_db, update_module, run_tests, get_third_party
```
I nuovi moduli custom vanno in `addons/<nome_modulo>/`, con versione `18.0.x.y.z` nel manifest.

## Comandi
- Installazione completa su un PC nuovo: `./scripts/setup_pc.sh` (idempotente: genera `.env`, OCA, db, test)
- Aggiornare un modulo: `./scripts/update_module.sh [modulo]`, che fa `-u` con Odoo fermo
- Test: `./scripts/run_tests.sh`. Esegui sempre i test dopo una modifica e aggiungine per ogni nuova logica.
- Log: `docker compose logs -f odoo` · Shell Odoo: `docker compose run --rm -T odoo odoo shell -d lab18 --no-http`
- Reset completo: `./scripts/reset_db.sh`, che chiede `SI`
- Il container gira come utente `odoo` e i mount sono in sola lettura per lui: i file si creano
  dall'host, non dal container.

## Regole di sviluppo
1. **Mai modificare il core di Odoo né il codice OCA.** Ogni modifica va in un modulo custom con
   `_inherit` (modelli) e `inherit_id` + xpath (viste). Se un modulo OCA ha un bug, lo si aggira nel
   modulo custom (esempio: `models/sale_subscription.py`, che aggiunge il listino mancante).
2. **OCA/terze parti: solo branch `18.0`.** Aggiungi il repo in `scripts/get_third_party.sh` e in
   `addons_path` di `config/odoo.conf`. Prima di usarlo verifica che `__manifest__.py` abbia versione
   `18.0.*` e `installable: True`.
3. Moduli Enterprise (`planning`, `project_forecast`, `industry_fsm`, `sale_subscription`) **non**
   sono disponibili: si costruisce l'equivalente nel modulo custom o si usa OCA.
4. Prima di fare un xpath, leggi la vista originale nel container
   (`/usr/lib/python3/dist-packages/odoo/addons/<modulo>/views/`).

## Ereditare i modelli principali in Odoo 18
| Modello | Note utili |
|---|---|
| `sale.order` / `sale.order.line` | Generazione progetto/task: `_timesheet_service_generation`, `_timesheet_create_project`, `_timesheet_create_task_prepare_values` (in `sale_project`/`sale_timesheet`). Qui `lab_sold_hours` = ore vendute. |
| `project.project` | `allocated_hours`, `privacy_visibility` (`followers`/`employees`/`portal`), `sale_line_id`. Qui `lab_*` ore/alert (calcolati, non salvati) e `_lab_check_hours_alert()`. |
| `project.task` | `allocated_hours` (= ore stimate), `effective_hours` (fogli ore, salvato), `sale_line_id`. Qui `lab_alert_level` e `lab_consumption_pct` (salvati, filtrabili). |
| `account.analytic.line` | Riga di foglio ore (`unit_amount` = ore, `amount` = costo negativo). L'override di create/write/unlink fa scattare l'alert. |
| `account.move` | `action_post` è bloccato per il Commerciale senza Amministrazione. |
| `product.template` | `service_policy` (`ordered_prepaid`, `delivered_timesheet`, ...), `service_tracking` (`task_in_project`, `project_only`, ...), più i campi `lab_hours_per_unit`, `lab_monthly_hours` e `lab_create_default_tasks`. |

Nelle viste di Odoo 18 si usa `<list>` (non `<tree>`), `invisible="espressione"` (non `attrs`), `<chatter/>`
e nel kanban `<t t-name="card">`. Il calendario non accetta `all_day="1"` (vuole un nome di campo) e i
filtri data non accettano `default_period="week"`.

## Regole d'oro del processo
- **Regola 80/20 per la pianificazione dei developer**: massimo **32h a settimana** allocate su
  Pianificazione (80% di 40h). Il restante 20% va a formazione, supporto e imprevisti. Il vincolo è in
  `lab.planning.slot._check_weekly_capacity` e il parametro è `lab_workflow_custom.max_weekly_hours`.
- **Conferma turno → consuntivazione automatica su Foglio Ore**: `lab.planning.slot.action_confirm`
  crea l'`account.analytic.line`. Non introdurre un secondo modo di consuntivare i turni.
- Alert monte ore al **75%** (giallo) e al **90%** (rosso): il task si misura sulle ore stimate, il
  progetto sulle ore vendute (per il canone AMS sul mese corrente).

## Owner per funzionalità
| Funzionalità | Owner |
|---|---|
| Opportunità, preventivi, ordini, fatture in bozza | Commerciale |
| Progetti, stime task, pianificazione turni, alert, margini | Project Manager |
| Conferma turni, fogli ore, task assegnati | Analista Funzionale / Sviluppatore |
| Conferma fatture, contabilità | Amministrazione |
