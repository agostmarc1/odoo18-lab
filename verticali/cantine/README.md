# Soluzione Cantina – Odoo 18 CE per le cantine delle Langhe

Prodotto standard della Software House Lab per cantine da 30.000 a 150.000 bottiglie/anno.
È nato su misura per **Cantina Bricco Rosso** (prima installazione, 120 ore). Ora è un pacchetto
ripetibile: ogni nuova cantina usa **lo stesso codice**, cambiano solo i suoi file di dati, e
l'installazione standard richiede **60 ore** invece di 120.

Ogni cantina ha il suo **Odoo dedicato** (in produzione un'istanza Cloudpepper; qui un container
sul tuo PC), separato dal laboratorio della software house sulla porta 8069.

## Cosa c'è nella cartella

| Cartella / file | A cosa serve |
|---|---|
| `addons/langhe_wine_ai/` | Modulo funzionale: anagrafica vino, ordini da email con Claude, schede IT/EN/DE, Packing List |
| `addons/cantina_standard/` | **Pacchetto standard**: installa vendite, magazzino con lotti e cartoni, acquisti, CRM, eventi, i 4 listini e le categorie; carica i dati del cliente dai suoi file |
| `addons/cantina_standard/modello_cliente/` | Modello dei file da compilare per una cantina nuova |
| `clienti/<cantina>/` | Dati di UNA cantina: `cliente.json`, `vini.csv`, `clienti.csv`, `ordine_demo.txt`; il file `.env` (porta e password) è generato e **non va su git** |
| `nuovo_cliente.sh` | Crea o completa l'Odoo dedicato di una cantina |
| `prova_pacchetto.sh` | Prova la soluzione su un Odoo 18 CE pulito (inglese, con e senza dati di esempio) e lancia i test |
| `docker-compose.yml`, `config/odoo.conf` | Un Odoo `odoo:18.0` ufficiale + PostgreSQL 16 per ogni cantina (progetto docker `cantina_<nome>`) |
| `docs/` | Architettura, manuale per la cantina, copione del video di 2 minuti |

## Accedere all'Odoo di Cantina Bricco Rosso

- Indirizzo: **http://127.0.0.1:8070**
- Amministratore: `admin`, password = `CANTINA_ADMIN_PASSWORD` in `clienti/bricco_rosso/.env`
- Utenti della cantina, password = `CANTINA_USERS_PASSWORD` nello stesso file:

| Login | Chi | Cosa può fare |
|---|---|---|
| `paolo` | Paolo Bricco, titolare | Vendite, magazzino, acquisti, fatture ed eventi come responsabile |
| `elena` | Elena Ferrero, commerciale export | Preventivi e ordini, clienti, eventi, consegne |
| `franco` | Franco Sobrero, cantina e magazzino | Consegne, lotti, inventario, acquisti |

Per provare subito: **Vendite → Preventivi → S00001 (Hudson Fine Wines)** → scheda *Assistente
Claude* → **Analizza Ordine con Claude AI**. Le righe che compaiono sono:
- Barolo 2020: 30 bottiglie (5 cartoni);
- Langhe Nebbiolo: 12 bottiglie;
- Barolo 2019 Magnum: 6.

Arrivano anche gli avvisi:
- per il Magnum ci sono solo 4 bottiglie libere;
- il Barbaresco 2016 non è in catalogo;
- il prezzo di 31 $ citato da Dave va verificato;
- la consegna è FOB Genova.

## Cantina nuova in 3 passi (scalabilità)

1. `./verticali/cantine/nuovo_cliente.sh "Tenuta Collina dei Noci"`: crea `clienti/collina_dei_noci/`
   dal modello e il file `.env` con la porta successiva (8071) e password casuali.
2. Compila i file della cartella. Di solito li prepara l'analista con la cantina, da Excel salvato
   in CSV con il `;`:
   - `cliente.json`: ragione sociale, indirizzo, utenti e ruoli;
   - `vini.csv`: codice, denominazione, annata, formato, cartone, pesi, i 4 prezzi, giacenza e lotto;
   - `clienti.csv`: nome, paese, lingua, listino.
3. Rilancia lo stesso comando. Lo script fa quattro cose:
   - crea il database in italiano;
   - imposta l'azienda in Italia e in euro;
   - installa contabilità italiana e pacchetto standard;
   - carica i dati e imposta le password.

Rilanciare il comando è sempre sicuro: carica solo ciò che manca e non tocca ciò che la cantina ha
già modificato. Per aggiornare i moduli dopo una nuova versione della soluzione:
`./verticali/cantine/nuovo_cliente.sh "Cantina Bricco Rosso" --aggiorna`.

## Claude: modalità demo e modalità reale

- **Senza chiave API (demo, laboratorio)**: l'analisi delle email e le schede tecniche usano regole
  scritte nel modulo (parole chiave, annate, quantità, prezzi citati, Incoterm). Nessuna chiamata
  esterna e nessuna credenziale. Le note dell'ordine dicono *Modalità demo*.
- **Con la chiave (produzione)**:
  - installare la libreria `anthropic` sul server (`pip install anthropic`, verificata con 2.9.0;
    su Cloudpepper va nei requirements dell'istanza);
  - inserire la chiave in **Impostazioni → Vendite → Assistente Claude**. È un parametro di sistema
    leggibile solo dagli amministratori; in alternativa si usa la variabile `ANTHROPIC_API_KEY`.

  Da quel momento risponde Claude, con lo stesso formato e gli stessi controlli: prezzi, giacenze e
  pesi li decide sempre Odoo.

| Parametro di sistema | Default | Note |
|---|---|---|
| `langhe_wine_ai.anthropic_api_key` | (vuota = demo) | Leggibile solo dagli amministratori |
| `langhe_wine_ai.model` | `claude-sonnet-5-5` | |
| `langhe_wine_ai.effort` | `medium` | `low` / `medium` / `high` |
| `langhe_wine_ai.use_fallback` | `True` | Fallback lato server se il modello rifiuta |

## Prove

- `./verticali/cantine/prova_pacchetto.sh`: Odoo ufficiale pulito, database solo in inglese, senza e
  con dati di esempio. I 12 test dei due moduli (`langhe_wine_ai` e `cantina_standard`) girano senza
  chiave API. Va lanciato prima di ogni commit che tocca `verticali/`.
- L'istanza di prova (progetto docker `cantina_prova`) viene cancellata alla fine. Le istanze dei
  clienti non si toccano.

## In produzione (Cloudpepper)

1. Nuova istanza Odoo 18 Community. Copiare `addons/langhe_wine_ai` e `addons/cantina_standard`
   nella cartella dei moduli custom.
2. Creare il database in italiano, con azienda in Italia ed euro **prima** della contabilità, come
   fa lo script. Poi installare `l10n_it` e `cantina_standard`.
3. Caricare i dati: dalla shell di Odoo
   `env['cs.customer.package']._cs_load('<cartella con i file del cliente>')`. In `cliente.json` va
   messo `"dati_demo": false`.
4. Configurare chiave Claude, server di posta e cambi automatici (il cambio USD di 1,08 è
   dimostrativo). Per la fatturazione elettronica e il resto della localizzazione italiana, OCA
   `l10n-italy` (vedi `docs/01_architettura_odoo18_ce.md`).

Fuori perimetro: i registri telematici **SIAN/ICQRF** restano nel software di cantina.
