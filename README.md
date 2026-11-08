# odoo18-lab – Laboratorio Odoo 18 Community

Ambiente di prova di **Odoo 18.0 Community Edition** per una software house / società di consulenza.
Flusso: **CRM → Vendite → Progetto → Pianificazione → Fogli ore → Alert monte ore → Fatturazione → Margini**.

Gira tutto dentro Docker: Odoo e il database PostgreSQL 16 sono in "scatole" separate.
Sul PC non si installa niente oltre a Docker e Git.

---

## Cosa c'è dentro

| Cartella / file | A cosa serve |
|---|---|
| `docker-compose.yml` | Dice a Docker quali container avviare (Odoo 18 + PostgreSQL 16) |
| `.env` | Password locali. **Non va mai su git** (copiarlo da `.env.example`) |
| `config/odoo.conf` | Configurazione di Odoo (cartelle dei moduli, database `lab18`) |
| `addons/lab_workflow_custom/` | **Il nostro modulo custom** |
| `third-party/` | Moduli OCA 18.0 scaricati con `scripts/get_third_party.sh` (non versionati) |
| `scripts/` | Comandi pronti: crea, resetta e aggiorna il database, lancia i test |

Moduli installati: `crm`, `sale_management`, `project`, `hr_timesheet`, `sale_timesheet`, `account`,
`subscription_oca` (OCA, canoni ricorrenti), `project_timeline` + `web_timeline` (OCA, timeline dei task)
e `lab_workflow_custom`.

> **Planning in Community:** i moduli `planning`, `project_forecast` e `industry_fsm` esistono solo in
> Odoo **Enterprise**. Per questo la Pianificazione (turni, regola 80/20, conferma → foglio ore) è
> costruita nel modulo `lab_workflow_custom` (app **Pianificazione**).

---

## Prima installazione sul tuo PC

### 1. Prerequisiti (una volta sola)

**Windows** (da PowerShell come amministratore):

```bash
wsl --install
```

(riavvia il PC se lo chiede), poi:

```bash
winget install -e --id Docker.DockerDesktop
```

```bash
winget install -e --id Git.Git
```

```bash
winget install -e --id GitHub.cli
```

Apri **Docker Desktop** e aspetta che diventi verde ("Engine running"). Se dice che la
virtualizzazione è disattivata: riavvia, entra nel BIOS (di solito tasto F2, F10 o Canc all'accensione),
attiva **Intel VT-x / Virtualization Technology** oppure **AMD SVM**, salva e riavvia.

> Consiglio Windows: lavora **dentro Ubuntu (WSL)**, non in `C:\Users\...`. Gli script sono per bash
> e il ricaricamento automatico del codice funziona bene solo sul disco di Linux.
> Apri il terminale "Ubuntu" e dai lì i comandi qui sotto.

**macOS:** installa Docker Desktop da docker.com e `brew install git gh`.
**Linux:** Docker Engine + plugin compose, `git`, `gh` dal gestore pacchetti.

### 2. Installa e avvia con un solo comando

Apri il terminale **Ubuntu** (su Windows: menu Start → "Ubuntu"; su Mac/Linux il Terminale), con
Docker Desktop acceso, e incolla:

```bash
git clone https://github.com/agostmarc1/odoo18-lab ~/odoo18-lab && ~/odoo18-lab/scripts/setup_pc.sh
```

Lo script, da solo:
1. crea il file `.env` con **password casuali**;
2. scarica i moduli OCA (solo branch 18.0);
3. crea il database `lab18` con i dati demo e installa tutti i moduli (5-10 minuti la prima volta);
4. lancia i test automatici (devono risultare `0 failed, 0 error(s) of 7 tests`);
5. stampa **link e credenziali**.

Si può rilanciare senza rischi: se il database è già installato non lo tocca.
Se dice che Docker non c'è o non è avviato: apri Docker Desktop → Impostazioni → Resources →
WSL integration → attiva **Ubuntu** → Apply, poi rilancia.

---

## Accesso

- Indirizzo: **http://127.0.0.1:8069** (raggiungibile solo dal tuo PC)
- Amministratore: utente `admin`, password = `LAB_ADMIN_PASSWORD` nel file `.env`
- Utenti di prova (password = `LAB_USERS_PASSWORD` nel file `.env`):

| Login | Nome | Ruolo (owner di processo) |
|---|---|---|
| `commerciale` | Carla Commerciale | Commerciale: CRM, Vendite, fatture **solo in bozza** |
| `pm` | Paolo Project Manager | Project Manager: Progetti, Pianificazione, Fogli ore, Report |
| `analista` | Anna Analista | Analista Funzionale: task assegnati, i miei turni, i miei fogli ore |
| `sviluppatore` | Davide Sviluppatore | Sviluppatore: task assegnati, i miei turni, i miei fogli ore |
| `amministrazione` | Alba Amministrazione | Amministrazione: Fatturazione completa e Vendite |

Per provare più utenti insieme usa una **finestra anonima** del browser per ognuno.

### Modalità sviluppatore (con "superpoteri")

- Dal menu: **Impostazioni** → in fondo alla pagina **Attiva la modalità sviluppatore**.
- Oppure dall'indirizzo: aggiungi `?debug=1` → `http://127.0.0.1:8069/odoo?debug=1`
  (con `?debug=assets` carica anche i file JS/CSS non compressi).
- I "superpoteri" (agire come superutente): con la modalità sviluppatore attiva, icona del 🐞
  in alto → **Diventa superutente**. Usalo solo per test: ignora i permessi.

---

## Uso quotidiano

| Cosa | Comando |
|---|---|
| Avviare Odoo | `docker compose up -d` |
| Fermare Odoo (i dati restano) | `docker compose stop` |
| Vedere i log in tempo reale | `docker compose logs -f odoo` (esci con Ctrl+C) |
| Stato dei container | `docker compose ps` |

### Aggiornare il modulo dopo una modifica al codice

```bash
./scripts/update_module.sh
```

(per un altro modulo: `./scripts/update_module.sh nome_modulo`). Poi ricarica la pagina.

Odoo gira con `--dev=xml,reload`: le modifiche **solo Python** vengono ricaricate da sole, mentre le
modifiche alle **viste XML** si vedono ricaricando la pagina. Per campi nuovi, dati, permessi e menu
serve sempre `update_module.sh`. Se il ricaricamento automatico non funziona (succede con cartelle
Windows montate in Docker), usa `docker compose restart odoo`.

### Test automatici

```bash
./scripts/run_tests.sh
```

Simulano l'intero flusso (7 test). Deve comparire `0 failed, 0 error(s) of 7 tests`.

### Resettare il database e ripartire da zero

```bash
./scripts/reset_db.sh
```

Chiede di scrivere `SI`, cancella il database `lab18` e i suoi allegati, poi lo ricrea con i dati demo
e tutti i moduli. Le password tornano quelle del file `.env`.

### Aggiornare i moduli OCA

```bash
./scripts/get_third_party.sh
```

Poi `./scripts/update_module.sh subscription_oca` (o il modulo interessato).

---

## Cosa fa il modulo `lab_workflow_custom`

### Prodotti pronti (Vendite → Prodotti)

| Prodotto | Fatturazione | Alla conferma dell'ordine | Ore |
|---|---|---|---|
| **Sviluppo Software a Corpo** | Prezzo fisso/prepagato | Nuovo progetto + task | 1 unità = **120h** (campo "Ore per unità") |
| **Pacchetto Monte Ore (50h)** | Prepagato | Nuovo progetto + task | 1 unità = **50h** |
| **Canone Assistenza Mensile AMS** | Prepagato, **ricorrente mensile** (OCA `subscription_oca`) | Nuovo progetto | **20h/mese** (campo "Ore mensili incluse") |

Per la variante "a consumo" (Time & Material) del monte ore: sul prodotto imposta
*Politica di fatturazione = In base ai fogli ore*.

### Task automatici sui progetti venduti

Alla conferma di un ordine con "Crea task di gestione interna", il progetto riceve 4 task e le ore
vendute vengono distribuite così:

| Task | % ore vendute |
|---|---|
| Analisi e Specifiche | 15% |
| Project Management & Coordinamento | 10% |
| Sviluppo – *nome prodotto* | 60% (la parte restante) |
| Test & UAT | 15% |

Percentuali e nomi si cambiano da **Progetti → Configurazione → Task di default commessa**.
Il progetto è visibile solo agli **utenti invitati**: gli sviluppatori vedono solo i task assegnati
a loro, mentre il commerciale dell'ordine viene aggiunto come follower.

### Monte ore e alert 75% / 90%

- **Task**: Ore vendute (riga d'ordine), **Ore stimate** (tempo allocato), **Ore consuntivate**
  (fogli ore) e % di consumo rispetto alle ore stimate.
- **Progetto**: Ore vendute, Ore stimate (somma dei task), Ore consuntivate e % di consumo rispetto
  alle ore vendute. Per il canone AMS il calcolo è sul **mese corrente**.
- **≥ 75%**: banner e badge gialli. **≥ 90%**: banner e badge rossi.
- Alla prima volta che il progetto supera una soglia arriva un **messaggio con attività** al PM
  (sul progetto) e al Commerciale (sull'ordine di vendita).
- Nella lista dei task ci sono i filtri **"Alert monte ore (≥75%)"** e **"Rischio sforamento (≥90%)"**.

### Pianificazione (app "Pianificazione")

- **Pianificazione team** (PM): calendario, lista e pivot dei turni. Un turno è *dipendente + giorno
  + progetto/task + ore*.
- **Regola 80/20**: massimo **32h a settimana** per persona. Oltre, Odoo blocca il salvataggio.
  Il valore si cambia in Impostazioni → Tecnico → Parametri di sistema →
  `lab_workflow_custom.max_weekly_hours`.
- Stati del turno: **Bozza** (solo il PM la vede) → **Pubblicato** (il dipendente lo vede in
  *I miei turni*) → **Confermato**. Alla conferma Odoo **crea la riga del Foglio ore**. Prima di
  confermare il dipendente può correggere le "Ore effettive".
- **Report → Carico settimanale**: ore pianificate per persona e per settimana.

### Permessi

- Il Commerciale può creare fatture **in bozza** ma non confermarle: la conferma spetta
  all'Amministrazione.

### Margini

**Progetti → Rendicontazione → Margini per commessa** (oppure Pianificazione → Report): una vista
pivot con Venduto, Fatturato, Costo fogli ore (ore × costo orario del dipendente) e Margine per
cliente e progetto. Ci sono anche i report standard di Odoo: Fogli ore → Rendicontazione e il
pannello *Redditività* nell'aggiornamento di progetto.

---

## Test end-to-end guidato del flusso

Usa una finestra del browser per ogni utente (le finestre anonime vanno bene).

1. **CRM – `commerciale`**: CRM → *Nuovo* → crea l'opportunità "Portale clienti" per un cliente
   (es. *Deco Addict*). Aprila → **Nuovo preventivo** → aggiungi la riga **Pacchetto Monte Ore (50h)**
   → Salva.
2. **Firma/Ordine – `commerciale`**: sul preventivo premi **Conferma** (diventa Ordine di vendita).
   Torna all'opportunità e premi **Vinta**.
3. **Progetto – `pm`**: Progetti → il nuovo progetto "S000xx - [MONTE-50H] ...". Nel progetto ci sono
   i 4 task (Analisi 7:30, PM 5:00, Sviluppo 30:00, Test 7:30). Nelle impostazioni del progetto
   imposta te stesso come *Project Manager*, poi assegna il task **Sviluppo** a *Davide Sviluppatore*.
   Se vuoi, correggi le stime dei task (campo *Tempo assegnato*).
4. **Pianificazione all'80% – `pm`**: Pianificazione → Pianificazione team → *Nuovo*.
   Crea 4 turni da 8h (lunedì–giovedì) per Davide sul task Sviluppo: sono 32h, cioè l'80%.
   Prova a crearne un quinto: Odoo lo blocca (regola 80/20). Poi seleziona i turni nella lista →
   **Pubblica**.
5. **Conferma turni – `sviluppatore`**: Pianificazione → **I miei turni** → **Conferma** su ogni turno.
   Ogni turno confermato crea una riga in *Fogli ore → I miei fogli ore*.
6. **Alert monte ore – `pm`**: dopo 32h il task Sviluppo (30h stimate) è **rosso**, mentre il progetto
   è a 32/50 = 64%. Aggiungi da *Fogli ore* altre 6h sul progetto: con 38h (76%) il progetto diventa
   **giallo**. A 45h (90%) diventa **rosso**. Controlla le attività ⏰ arrivate al PM e, sull'ordine
   di vendita, al Commerciale.
7. **Fatturazione**: `commerciale` → ordine di vendita → **Crea fattura** → bozza (se prova a
   confermarla riceve un errore: è voluto). `amministrazione` → Contabilità → Fatture → apri la
   bozza → **Conferma**.
8. **Margini – `pm`**: Progetti → Rendicontazione → **Margini per commessa**: trovi venduto 2.750 €,
   fatturato, costo delle ore (Davide costa 35 €/h) e margine.

---

## Problemi comuni

- **La pagina non si apre**: `docker compose ps` (i container sono "Up"?) e
  `docker compose logs -f odoo`.
- **"Manca il file .env"**: copia `.env.example` in `.env`.
- **Porta 8069 occupata**: un altro Odoo è acceso. Fermalo, oppure cambia `127.0.0.1:8069:8069` in
  `127.0.0.1:8070:8069` in `docker-compose.yml`.
- **Errore 429 / "Too Many Requests" scaricando le immagini**: Docker Hub limita i download
  anonimi. Fai `docker login` oppure riprova più tardi.
