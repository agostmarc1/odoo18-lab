# odoo18-lab – Laboratorio Odoo 18 Community

Ambiente di prova di **Odoo 18.0 Community Edition** per una software house / società di consulenza.
Flusso: **CRM → Vendite → Progetto → Pianificazione → Fogli ore → Alert monte ore → Fatturazione → Margini**.

Gira tutto dentro Docker: Odoo e il database PostgreSQL 16 sono in "scatole" separate.
Sul PC non si installa niente oltre a Docker e Git.

---

## Dati sintetici: solo la nostra software house

Il database `lab18` **non** contiene i dati demo standard di Odoo (niente arredamento, "Costruzione
casa", aziende di Chicago): si vedono solo dati coerenti con il nostro flusso, creati da
`models/lab_demo_data.py` con date relative a oggi.

| Cliente | Contratto | Cosa si verifica |
|---|---|---|
| Rossi Meccanica | Monte ore 50h | alert giallo all'80%, ore per task, fattura anticipata, consulente fatturato (solo costo) |
| Bianchi Logistica | T&M 60h | fattura di Carlo ribaltata +15%, spese vive AI, ore parallele approvate e da approvare |
| Verdi Retail | Canone AMS 20h/mese | 7 ticket di assistenza collegati alla commessa (chiusi con valutazione, in corso, in attesa del cliente, urgente con SLA scaduto), ore sui ticket, consumo del mese |
| Neri Assicurazioni | Sviluppo a corpo 120h | task di analisi oltre il 90%, ore del consulente in attesa di fattura |

In più: 3 opportunità e un preventivo AMS in bozza (Commerciale), turni della settimana (Niccolò a
32h, Carlo con fattore 1,5), mese scorso dei costi AI chiuso dall'Amministrazione, un ticket di
Rossi Meccanica ancora da smistare (monte ore: la commessa la sceglie il Supporto).

## Azienda demo: Italia, euro, localizzazione italiana

Il database `lab18` nasce già come azienda italiana (**Software House Lab S.r.l.**, valuta **euro**,
lingua italiana, piano dei conti e IVA italiani) con **tutta la localizzazione italiana OCA 18.0**
(`l10n-italy`: fatturazione elettronica SdI/PEC, registri IVA, liquidazione IVA, RiBa, DDT,
cespiti, bilancio, Intrastat, codice fiscale...). La valuta va scelta alla creazione del database:
dopo le prime registrazioni contabili Odoo non permette più di cambiarla.

La localizzazione è **configurazione dell'ambiente**, non una personalizzazione: per questo non è
una dipendenza della nostra app (che resta installabile anche in un Odoo non italiano). L'elenco dei
moduli è in `scripts/_lib.sh` (`ITALY_MODULES`); i repository OCA in `scripts/get_third_party.sh`.

L'immagine Docker è quella ufficiale `odoo:18.0` più due librerie Python richieste da `l10n-italy`
(`Dockerfile`, `requirements.txt` con versioni fissate).

## Cosa c'è dentro

| Cartella / file | A cosa serve |
|---|---|
| `docker-compose.yml` | Dice a Docker quali container avviare (Odoo 18 + PostgreSQL 16) |
| `Dockerfile`, `requirements.txt` | Immagine `odoo:18.0` + librerie per la localizzazione italiana |
| `.env` | Password locali. **Non va mai su git** (copiarlo da `.env.example`) |
| `config/odoo.conf` | Configurazione di Odoo (cartelle dei moduli, database `lab18`) |
| `addons/lab_workflow_custom/` | **Il nostro modulo custom** |
| `third-party/` | Moduli OCA 18.0 scaricati con `scripts/get_third_party.sh` (non versionati) |
| `scripts/` | Comandi pronti: crea, resetta e aggiorna il database, lancia i test |

**Tutte le personalizzazioni sono in una sola app: "Flusso Operativo Software House"**
(nome tecnico `lab_workflow_custom`). Si installa solo lei: Odoo attiva da solo i moduli da cui dipende,
cioè `crm`, `sale_management`, `project`, `hr_timesheet`, `sale_timesheet`, `account`,
`subscription_oca` (OCA, canoni ricorrenti), `project_timeline` + `web_timeline` (OCA, timeline dei task)
e l'**Helpdesk OCA** per i ticket (`helpdesk_mgmt_timesheet`, `helpdesk_type`, `helpdesk_mgmt_sla`,
`helpdesk_mgmt_rating`, `website_helpdesk_mgmt`, che porta anche il modulo **Sito web** di Odoo).

> **Helpdesk in Community:** l'app *Helpdesk* di Odoo è solo Enterprise. Si usa quella OCA
> (`helpdesk_mgmt`, repo `OCA/helpdesk` branch 18.0), personalizzata dalla nostra app.

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

### Alternativa Windows senza Ubuntu: Docker Desktop + Git Bash

Se `wsl --install` non riesce a scaricare (es. errore "Timeout del gateway (504)"):
1. Dal browser scarica e installa **Docker Desktop** (https://www.docker.com/products/docker-desktop/)
   e **Git per Windows** (https://git-scm.com/download/win). Riavvia se richiesto.
2. Se Docker Desktop chiede di aggiornare WSL e fallisce: scarica il file `.x64.msi` da
   https://github.com/microsoft/WSL/releases, aprilo, riavvia.
3. Apri Docker Desktop e aspetta "Engine running".
4. Apri **Git Bash** (menu Start) e incolla il comando del punto 2 qui sotto.

Nota: con le cartelle Windows il ricaricamento automatico del codice può non funzionare; dopo una
modifica usa `docker compose restart odoo` oppure `./scripts/update_module.sh`.

### 2. Installa e avvia con un solo comando

Apri il terminale **Ubuntu** (su Windows: menu Start → "Ubuntu", oppure **Git Bash**; su Mac/Linux il Terminale), con
Docker Desktop acceso, e incolla:

```bash
git clone https://github.com/agostmarc1/odoo18-lab ~/odoo18-lab && ~/odoo18-lab/scripts/setup_pc.sh
```

Lo script, da solo:
1. crea il file `.env` con **password casuali**;
2. scarica i moduli OCA (solo branch 18.0);
3. crea il database `lab18` (Italia, euro) con la localizzazione italiana e la nostra app, **senza i
   dati demo standard di Odoo**, e carica i **dati sintetici** della software house (15-25 minuti la
   prima volta);
4. lancia i test automatici (devono risultare `0 failed, 0 error(s) of 19 tests`);
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
| `giuseppe` | Giuseppe Commerciale | Commerciale: CRM, Vendite, fatture **solo in bozza** |
| `marco` | Marco Project Manager | Project Manager: Progetti, Pianificazione, Fogli ore, Costi e AI, Report |
| `carlo` | Carlo Sviluppatore | Sviluppatore senior, **consulente esterno** (fattura 360 €/giorno, fattore parallelo 1,5) |
| `niccolo` | Niccolò Sviluppatore | Sviluppatore junior, **consulente esterno** (fattura 280 €/giorno, fattore 1,0) |
| `giulia` | Giulia Analista | Analista funzionale (38 €/h): task assegnati, turni, fogli ore |
| `gianluca` | Gianluca Analista | Analista funzionale (38 €/h): task assegnati, turni, fogli ore |
| `nicola` | Nicola Supporto | Supporto AMS (30 €/h): come il team, e segue in automatico le commesse a canone |
| `luana` | Luana Amministrazione | Amministrazione: Fatturazione completa, fatture dei consulenti, chiusura mese costi |
| `mario.verdi@verdiretail.example` | Mario Verdi | **Cliente (portale)** di Verdi Retail: Kanban dei ticket della sua azienda |
| `luca.rossi@rossimeccanica.example` | Luca Rossi | **Cliente (portale)** di Rossi Meccanica: vede solo i ticket di Rossi |

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

Simulano l'intero flusso e i costi di commessa (19 test). Deve comparire `0 failed, 0 error(s) of 19 tests`.

### Resettare il database e ripartire da zero

```bash
./scripts/reset_db.sh
```

Chiede di scrivere `SI`, cancella il database `lab18` e i suoi allegati, poi lo ricrea con tutti i moduli
e i dati sintetici. Le password tornano quelle del file `.env`.

### Aggiornare i moduli OCA

```bash
./scripts/get_third_party.sh
```

Poi `./scripts/update_module.sh subscription_oca` (o il modulo interessato).

---

## Installare l'app in un altro Odoo 18

```bash
./scripts/package_app.sh
```

Crea `dist/flusso_operativo_18.0.zip`: dentro ci sono l'app e i moduli OCA 18.0 che le servono,
più un file `LEGGIMI.txt` con le istruzioni. Nell'altro Odoo 18.0 Community si copiano tutte le
cartelle nella cartella dei moduli, si riavvia Odoo e poi si va in **Applicazioni → Aggiorna elenco
applicazioni → "Flusso Operativo Software House" → Installa**.
Gli utenti di prova e lo scenario sintetico si creano solo nei database con dati demo; altrimenti i
ruoli si assegnano da Impostazioni → Utenti (sezione "Ruoli Flusso Operativo"). La descrizione
dell'app (Applicazioni → Flusso Operativo Software House) contiene la documentazione funzionale con
screenshot annotati e diagrammi BPMN.

Regola: **ogni nuova personalizzazione va dentro questa app**, mai in impostazioni fatte a mano o
in altri moduli, altrimenti non viaggia con il pacchetto.

## Cosa fa l'app `lab_workflow_custom`

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

### Costi commessa: AI, lavoro in parallelo, consulenti esterni

Chi segna le ore lo fa come sempre: i costi accessori li calcola e li ripartisce Odoo.

- **Lavoro in parallelo.** Se in un giorno una persona segna più ore di quelle del suo calendario
  (es. 6h + 6h su due commesse in una giornata da 8h), le ore restano fatturabili ma il **costo**
  della giornata si divide tra le commesse (8h × costo orario, non 12h). Sui contratti T&M quelle
  ore vanno approvate dal PM prima della fattura: **Pianificazione → Ore parallele da approvare**.
- **Fattore parallelo.** Nella scheda della persona (scheda *Costi e AI*): quante ore-progetto
  può gestire per ogni ora reale (es. senior con Claude Code 1,5). Il limite settimanale della
  regola 80/20 diventa 32h × fattore. Il PM lo può correggere per una settimana:
  **Pianificazione → Fattore parallelo per settimana**.
- **Licenze AI (Claude Team/Pro, Claude Code).** Si assegnano nella scheda della persona o in
  **Pianificazione → Costi e AI → Licenze AI**. Odoo calcola la *maggiorazione AI all'ora*
  (licenze / ore standard del mese) e il *costo pieno all'ora*. Ogni notte ripartisce le licenze
  sulle commesse in proporzione alle ore; a fine mese l'Amministrazione preme **Chiudi mese**
  (calcolo esatto: licenza × ore commessa / ore totali). Per PM e analisti si può scegliere la
  ripartizione *governance*: sulle commesse di cui sono Project Manager.
- **Consulenti esterni.** Nella scheda persona: *Tipo risorsa = Consulente esterno*, fornitore e
  tariffa (all'ora o a giornata). Finché la fattura non arriva la commessa vede il costo
  *maturato* (ore × tariffa). Sulla fattura fornitore usa il prodotto **Prestazione consulente
  esterno**, la distribuzione analitica della commessa e la colonna *Consulente*: alla conferma
  Odoo collega le sue ore e mostra lo *scostamento* fattura − ore.
- **Ribaltamento al cliente (pass-through).** Solo sui contratti **a consuntivo (T&M)**: la
  fattura del consulente (o una spesa viva con il prodotto *Spese vive ribaltate*) si aggiunge da
  sola all'ordine del cliente al costo + **ricarico 15%** (modificabile sulla commessa, 0% = al
  puro costo). Sui contratti a corpo e sui canoni il costo resta un costo e riduce il margine.
  Sui T&M le ore del consulente non si fatturano anche a ore, per non fatturarle due volte.

### Margini

**Progetti → Rendicontazione → Margini per commessa** (oppure Pianificazione → Report): per ogni
commessa Venduto (T&M = ore consegnate × prezzo), Ribaltato al cliente, Costo lavoro interno,
Costo AI, Costo consulenti esterni (con la quota maturata in attesa di fattura), Altri costi
fornitori, Margine,
Margine % e Margine senza pass-through, più le *ore risparmiate* (stimate − consuntivate) che
mostrano l'effetto dell'AI sui contratti a corpo. Ci sono anche i report standard di Odoo:
Fogli ore → Rendicontazione e il pannello *Redditività* nell'aggiornamento di progetto.

### Consumi AI a consumo (API Anthropic, Claude Code)

**Pianificazione → Costi e AI → Consumi AI.** Ogni riga è un consumo (giorno, workspace, chiave API,
utente, importo). Le righe arrivano da tre fonti, con lo stesso risultato:

1. **a mano**, direttamente nella lista;
2. **da file CSV** (es. export dalla Console Anthropic): Preferiti → *Importa record*;
3. **dal connettore Anthropic** (pulsante *Importa da Anthropic* e job notturno). È **facoltativo e
   spento in questo ambiente demo**: si attiva solo se l'amministratore imposta una chiave Admin nel
   parametro di sistema `lab_workflow_custom.anthropic_admin_key`. Senza chiave tutto il resto funziona.

**Corrispondenze consumi** decide a chi va ogni costo, senza toccare il codice:

| Il consumo ha... | Dove va il costo |
|---|---|
| un workspace o una chiave API dedicati a una commessa | tutto su quella commessa (**diretto**) |
| un utente (es. il Claude Code di Carlo) | alla persona, poi diviso sulle sue commesse in base alle ore del mese |
| nessuna corrispondenza | costi generali (evidenziati in giallo, da sistemare) |

Una corrispondenza aggiunta dopo vale anche per i consumi già registrati (non per i mesi chiusi).
Alla **chiusura del mese**, i consumi diretti delle commesse **T&M** diventano una riga *Spese vive AI
mm/aaaa* sull'ordine del cliente, al costo + ricarico, pronta da fatturare. Riaprendo il mese (se non
ancora fatturata) la spesa torna a zero e si ricalcola alla nuova chiusura, senza doppioni.

Nei dati sintetici ci sono tre consumi del mese scorso, uno per caso: diretto (workspace della
commessa Bianchi Logistica), personale (Claude Code di Carlo) e senza corrispondenza.

### Ticket di assistenza (app "Helpdesk")

- **Come arrivano.** Email all'indirizzo dell'assistenza (alias `assistenza@` + dominio della posta),
  modulo pubblico **Assistenza** sul sito (http://127.0.0.1:8069/assistenza, senza login) oppure
  portale clienti (*I miei ticket*). Il contatto si riconosce dall'email.
- **Kanban nel portale.** I clienti seguono i propri ticket in *I miei ticket → Vista Kanban*
  (http://127.0.0.1:8069/my/tickets/kanban): colonne per fase, aggiornate in tempo reale quando il
  Supporto sposta un ticket. Ogni cliente vede solo i ticket della propria azienda (regola di
  sicurezza del database, valida anche se è follower del ticket di un altro cliente).
- **Conferma via email.** Il ticket dal sito nasce *da confermare*: il cliente riceve un'email con
  il pulsante **Conferma la richiesta** e solo dopo il ticket si collega all'azienda e alla commessa
  (nessuno può aprire ticket a nome di un altro cliente). Chi è collegato con il proprio account e usa
  la propria email non conferma. Il Supporto vede l'avviso e il filtro *Da confermare* e può
  confermare a mano; le richieste mai confermate si archiviano dopo 7 giorni
  (`lab_workflow_custom.helpdesk_web_confirm_days`). Nel lab l'email resta in coda: il link si legge
  in Impostazioni → Tecnico → Email.
- **Descrizione come una email.** Nel modulo del sito la descrizione ha una barra con grassetto,
  corsivo, sottolineato, elenchi, link e immagini; le schermate si incollano con Ctrl+V o si
  trascinano. Le immagini diventano allegati del ticket; il testo viene ripulito da codice pericoloso.
- **Commessa.** Se il cliente ha un **canone AMS**, il ticket va da solo sulla sua commessa: le ore
  segnate sul ticket (scheda *Fogli ore*) scalano le 20h del mese e fanno scattare gli alert 75%/90%.
  Per monte ore, T&M e a corpo la commessa (e il task) li sceglie il Supporto.
- **SLA** (Helpdesk → Configurazione → SLA): AMS presa in carico entro 4 ore lavorative se urgente,
  8 se alta, 2 giorni altrimenti; risoluzione entro 5 giorni; senza canone presa in carico entro
  3 giorni. In *In attesa* (del cliente) il tempo si ferma. Filtro *SLA scaduto* nella lista.
- **Email al cliente**, in italiano: ricevuto, preso in carico, in attesa di una tua risposta,
  risolto (+ richiesta di valutazione da 1 a 5). Ogni email ha il pulsante **Segui il ticket**: apre la
  pagina del ticket anche senza account. Le risposte del Supporto arrivano per email e il cliente
  risponde dalla sua casella.
- **Chi fa cosa.** Supporto (`nicola`): tutti i ticket. PM (`marco`): responsabile Helpdesk, SLA e
  configurazione. Commerciale (`giuseppe`): vede in sola lettura i ticket dei suoi clienti.
- **Anti-spam del modulo pubblico**: campo esca nascosto e massimo 5 ticket all'ora per indirizzo
  (parametro `lab_workflow_custom.helpdesk_web_max_per_hour`). In produzione si aggiungono le chiavi
  reCAPTCHA (Impostazioni → Sito web).
- **In questo laboratorio non c'è un server di posta**: le email in uscita restano in coda e quelle
  in arrivo si provano con i test. In produzione: Impostazioni → Generali → *Dominio alias* e
  Impostazioni → Tecnico → *Server di posta in arrivo*.

### Prossima fase (non ancora fatta)

- **Fase 3:** commit Git come base di ripartizione dei costi AI (in alternativa o insieme alle ore).

---

## Video dimostrativo e documentazione dell'app

Nella scheda dell'app (Applicazioni → *Flusso Operativo Software House*) ci sono:

- il **video dimostrativo** (`static/description/demo_flusso_operativo.mp4`), con capitoli e didascalie;
- la **guida passo-passo** per ruolo (sezione 3 della pagina);
- il link all'**analisi funzionale e tecnica** per i tecnici
  (`static/description/analisi_tecnica.html`, anche su
  http://127.0.0.1:8069/lab_workflow_custom/static/description/analisi_tecnica.html).

Dopo una modifica all'app il video si rigenera con Odoo avviato:

```bash
./scripts/registra_video.sh          # registra il video (circa 6 minuti)
./scripts/registra_video.sh --prova  # solo schermate di controllo in dist/video_lavoro
```

Lo script guida Chrome con Playwright (ambiente `.venv-video`, creato da solo la prima volta) e monta
il video con il ffmpeg del PC. Crea un ordine di prova per *Ferri Automazione S.r.l.* e alla
registrazione successiva lo cancella, insieme a progetto, turni e fogli ore.

---

## Test end-to-end guidato del flusso

Usa una finestra del browser per ogni utente (le finestre anonime vanno bene).

1. **CRM – `giuseppe`**: CRM → *Nuovo* → crea l'opportunità "Portale clienti" per un cliente
   (es. *Deco Addict*). Aprila → **Nuovo preventivo** → aggiungi la riga **Pacchetto Monte Ore (50h)**
   → Salva.
2. **Firma/Ordine – `giuseppe`**: sul preventivo premi **Conferma** (diventa Ordine di vendita).
   Torna all'opportunità e premi **Vinta**.
3. **Progetto – `marco`**: Progetti → il nuovo progetto "S000xx - [MONTE-50H] ...". Nel progetto ci sono
   i 4 task (Analisi 7:30, PM 5:00, Sviluppo 30:00, Test 7:30). Nelle impostazioni del progetto
   imposta te stesso come *Project Manager*, poi assegna il task **Sviluppo** a *Niccolò Sviluppatore*.
   Se vuoi, correggi le stime dei task (campo *Tempo assegnato*).
4. **Pianificazione all'80% – `marco`**: Pianificazione → Pianificazione team → *Nuovo*.
   Crea 4 turni da 8h (lunedì–giovedì) per Niccolò sul task Sviluppo: sono 32h, cioè l'80%
   (con Carlo, fattore parallelo 1,5, il limite sarebbe 48h).
   Prova a crearne un quinto: Odoo lo blocca (regola 80/20). Poi seleziona i turni nella lista →
   **Pubblica**.
5. **Conferma turni – `niccolo`**: Pianificazione → **I miei turni** → **Conferma** su ogni turno.
   Ogni turno confermato crea una riga in *Fogli ore → I miei fogli ore*.
6. **Alert monte ore – `marco`**: dopo 32h il task Sviluppo (30h stimate) è **rosso**, mentre il progetto
   è a 32/50 = 64%. Aggiungi da *Fogli ore* altre 6h sul progetto: con 38h (76%) il progetto diventa
   **giallo**. A 45h (90%) diventa **rosso**. Controlla le attività ⏰ arrivate al PM e, sull'ordine
   di vendita, al Commerciale.
7. **Fatturazione**: `giuseppe` → ordine di vendita → **Crea fattura** → bozza (se prova a
   confermarla riceve un errore: è voluto). `luana` → Contabilità → Fatture → apri la
   bozza → **Conferma**.
8. **Margini – `marco`**: Progetti → Rendicontazione → **Margini per commessa**: trovi venduto 2.750 €,
   fatturato, costo delle ore e margine. Niccolò è un consulente esterno: finché non arriva la sua
   fattura la commessa vede il costo *maturato* (ore × 280 €/giorno = 35 €/h); quando `luana`
   registra la fattura fornitore (prodotto *Prestazione consulente esterno*, colonna *Consulente*)
   il costo maturato viene sostituito da quello fatturato e compare lo scostamento. Tutti gli importi sono in euro
   e le fatture usano il piano dei conti e l'IVA italiani (22%).
9. **Ticket – cliente e `nicola`**: in una finestra anonima apri http://127.0.0.1:8069/assistenza e
   invia una richiesta con l'email `helpdesk@verdiretail.example` (Verdi Retail, canone AMS).
   `nicola` → Helpdesk → Ticket: il ticket è già sulla commessa AMS con i suoi SLA. *Assegna a me*,
   portalo a *In corso*, segna 1h nella scheda *Fogli ore* e chiudilo con *Fatto*. Sulla commessa il
   consumo del mese sale di 1h. `giuseppe` vede il ticket ma non lo può modificare.
   In un'altra finestra anonima entra come `mario.verdi@verdiretail.example` e apri *I miei ticket →
   Vista Kanban*: quando `nicola` cambia fase, la scheda si sposta da sola. Con
   `luca.rossi@rossimeccanica.example` i ticket di Verdi non si vedono.

---

## Problemi comuni

- **La pagina non si apre**: `docker compose ps` (i container sono "Up"?) e
  `docker compose logs -f odoo`.
- **"Manca il file .env"**: copia `.env.example` in `.env`.
- **Porta 8069 occupata**: un altro Odoo è acceso. Fermalo, oppure cambia `127.0.0.1:8069:8069` in
  `127.0.0.1:8070:8069` in `docker-compose.yml`.
- **Errore 429 / "Too Many Requests" scaricando le immagini**: Docker Hub limita i download
  anonimi. Fai `docker login` oppure riprova più tardi.
