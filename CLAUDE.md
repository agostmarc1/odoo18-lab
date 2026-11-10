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
- **Odoo 18.0 Community Edition**, immagine `odoo18-lab:18.0` costruita dal `Dockerfile` sopra
  `odoo:18.0` (mai `latest`) + librerie di `requirements.txt` (versioni fissate), PostgreSQL 16.
- Azienda demo **italiana in euro** con tutta la localizzazione OCA `l10n-italy` 18.0 (`ITALY_MODULES`
  in `scripts/_lib.sh`). Paese e valuta si impostano in `init_db.sh` PRIMA della contabilità.
  La localizzazione è configurazione d'ambiente: NON metterla in `depends` dell'app.
- Utenti demo: giuseppe (Commerciale), marco (PM), carlo e niccolo (Sviluppatori, consulenti
  esterni), giulia e gianluca (Analisti funzionali), nicola (Supporto AMS), luana (Amministrazione).
- Database unico: `lab18`, creato **senza i dati demo standard di Odoo** (`--without-demo=all`) e con
  lo scenario sintetico dell'app (`lab.demo.data._lab_load_synthetic`, idempotente, date relative a oggi;
  in altri db parte con i dati demo dell'app). Se aggiungi una funzionalità, aggiungi allo scenario i dati
  che la mostrano. Odoo è su http://127.0.0.1:8069.
- La documentazione per l'utente sta in `static/description/index.html` (pagina dell'app): aggiornala
  insieme alla specifica quando cambia una funzionalità.
- Dev mode: `--dev=xml,reload` nel `command` di `docker-compose.yml`. Odoo 18 **non** legge `dev_mode` da `odoo.conf`.
- Credenziali solo in `.env` (gitignored). **Mai password o token in file versionati.** Gli utenti demo
  non hanno password nell'XML: le imposta `scripts/init_db.sh` leggendole da `.env`.

## Struttura
```
docker-compose.yml   config/odoo.conf   .env(.example)
addons/lab_workflow_custom/   <- moduli custom (mount /mnt/extra-addons)
third-party/oca-*            <- repo OCA branch 18.0 (mount /mnt/third-party, gitignored)
scripts/                     <- setup_pc, init_db, reset_db, update_module, run_tests, get_third_party, package_app
dist/                        <- pacchetto dell'app per altri Odoo (gitignored)
```
**Una sola app**: tutte le personalizzazioni rispetto a Odoo 18 CE stanno in `lab_workflow_custom`
("Flusso Operativo Software House", `application: True`). Niente configurazioni a mano nel database né
altri moduli custom: campi, viste, dati, parametri, gruppi e permessi vanno nell'app, così installandola
in un altro Odoo si attiva tutto. Ogni modulo (standard o OCA) che serve va in `depends` del manifest;
se è OCA va anche nell'elenco `OCA` di `scripts/package_app.sh`. A ogni modifica alza la versione
`18.0.x.y.z` nel manifest. `scripts/_lib.sh` installa solo `lab_workflow_custom` (le dipendenze arrivano da sole).

## Comandi
- Installazione completa su un PC nuovo: `./scripts/setup_pc.sh` (idempotente: genera `.env`, OCA, db, test)
- Pacchetto per un altro Odoo 18: `./scripts/package_app.sh` (crea `dist/flusso_operativo_18.0.zip` con app + moduli OCA)
- Video dell'app: `./scripts/registra_video.sh` (Odoo avviato; `--prova` = solo schermate). Rigeneralo quando
  cambia un flusso mostrato; se cambia una vista, aggiorna prima il copione in `scripts/registra_video.py`.
  Documentazione per i tecnici: `static/description/analisi_tecnica.html` (aggiornala insieme a `index.html`).
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
- **Costi in parallelo**: se una persona segna in un giorno più ore del suo calendario, il costo
  di ogni riga è ore × costo orario × (ore calendario / ore segnate); le ore restano fatturabili ma
  vanno approvate dal PM (`lab_parallel_state`) e finché non lo sono non entrano nel consegnato T&M.
  Logica in `account.analytic.line._lab_recompute_days`. Non cambiare `unit_amount`.
- **Fattore parallelo**: limite settimanale 80/20 × `hr.employee.lab_parallel_factor`, correggibile per
  settimana con `lab.planning.capacity`.
- **Licenze AI**: `lab.ai.license` → `lab.cost.period` / `lab.cost.allocation` (mese in corso:
  maggiorazione oraria; mese finito/chiuso: licenza × ore commessa / ore totali). Il report margini
  legge le allocazioni. La chiusura del mese spetta all'Amministrazione.
- **Consumi AI** (fase 2): `lab.ai.usage` (fonti manuale / CSV / API) + `lab.ai.mapping`
  (workspace/chiave → commessa = diretto; actor → persona = ripartito sulle ore; nulla = costi
  generali). Ripartizione in `lab.cost.period._compute_ai_variable`; alla chiusura i diretti delle
  commesse T&M diventano spesa viva sull'ordine (`_create_ai_passthrough`).
- **Ambiente demo**: nessuna integrazione deve richiedere credenziali reali. Il connettore Anthropic
  (`_lab_fetch_anthropic`, API Usage & Cost Analytics) si attiva solo se esiste il parametro
  `lab_workflow_custom.anthropic_admin_key`; si testa con payload d'esempio (`_lab_parse_anthropic_rows`),
  mai con chiamate reali. Le chiavi stanno solo nei parametri di sistema, mai in file versionati.
- **Consulenti esterni**: `lab_resource_type = external`, costo orario 0, costo maturato in
  `lab_accrued_external_cost` finché la fattura fornitore (riga con `lab_consultant_id`) non lo sostituisce.
- **Pass-through**: l'ordine da rifatturare si cerca con `sudo` (le commesse sono riservate e chi
  conferma la fattura, es. l'Amministrazione, spesso non le vede). Testare sempre i flussi con gli
  utenti dei ruoli, non solo come superutente.
- **Valute**: i tassi vanno riallineati all'euro alla creazione del db (`setup_company_italy`); il cambio
  USD dei dati demo e' dimostrativo (1,08).
- **Pass-through** solo sui contratti T&M (`project._lab_contract_type() == 'tm'`), con ricarico
  `lab_passthrough_markup_pct` (default 15, parametro `lab_workflow_custom.passthrough_markup_pct`),
  usando la rifatturazione spese standard di Odoo (`expense_policy = cost`).
- **Tracciabilità pacchetti**: sulle commesse vendute a ore (contratto a corpo/monte ore o T&M) il foglio
  ore senza task non si salva (`account.analytic.line._check_lab_task_required`; i canoni AMS restano
  liberi). Ogni riga d'ordine mostra ore scalate/residue e il dettaglio per task
  (`sale.order.line.action_lab_open_consumption`). Il progetto ha la scheda "Costi, ricavi e margine",
  che legge `lab.margin.report`: un solo calcolo dei margini, mai duplicarlo.
- Alert monte ore al **75%** (giallo) e al **90%** (rosso): il task si misura sulle ore stimate, il
  progetto sulle ore vendute (per il canone AMS sul mese corrente).

## Owner per funzionalità
| Funzionalità | Owner |
|---|---|
| Opportunità, preventivi, ordini, fatture in bozza | Commerciale |
| Progetti, stime task, pianificazione turni, alert, margini | Project Manager |
| Conferma turni, fogli ore, task assegnati | Analista Funzionale / Sviluppatore |
| Assistenza sulle commesse a canone (AMS): task, fogli ore | Supporto |
| Conferma fatture, contabilità | Amministrazione |
| Licenze AI, consumi AI e import, fatture consulenti, chiusura mese costi | Amministrazione |
| Corrispondenze consumi AI (workspace/chiavi/utenti → commesse/persone) | Project Manager, Amministrazione |
| Approvazione ore parallele, fattore parallelo, ricarico pass-through | Project Manager |
