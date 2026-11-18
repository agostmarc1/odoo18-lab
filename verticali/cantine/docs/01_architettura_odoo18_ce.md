# Deliverable 1 – Architettura Odoo 18 CE per cantine delle Langhe

Target: cantine da 30.000 a 150.000 bottiglie l'anno, su Odoo 18.0 Community ospitato su Cloudpepper.
Perimetro: tutto ciò che viene **dopo l'imbottigliamento** (anagrafica vini, lotti, listini, ordini,
export, DDT, fatturazione, vendita diretta, enoturismo).
**Fuori perimetro:** registri telematici SIAN/ICQRF, dichiarazioni di vendemmia e produzione,
documenti di accompagnamento accise (e-DAS / e-AD / EMCS). Restano nel software verticale di cantina.
Odoo tiene il numero di lotto, che è lo stesso stampato in etichetta e registrato nel verticale:
la chiave di raccordo tra i due sistemi è **codice prodotto + lotto**.

> Legenda: ✅ = verificato sul nostro laboratorio Odoo 18 (sorgenti standard o repository OCA 18.0
> presenti in `odoo18-lab/third-party`). 🔎 = repository OCA non presente nel laboratorio: verificare
> che il modulo esista sul branch 18.0 prima di metterlo in offerta.

---

## 0. Il pacchetto standard: uguale per ogni cantina

La soluzione si installa con **un solo modulo**, `cantina_standard`. Porta con sé:
- i moduli standard che servono sempre: vendite, magazzino con consegne, acquisti, CRM, eventi,
  contatti e fatturazione;
- il modulo `langhe_wine_ai`;
- la configurazione comune: lotti, cartoni (*packagings*) e listini attivi, i 4 listini Italia /
  Ho.Re.Ca. / Export Europa / Export USA, le categorie Vini › Rossi / Bianchi / Spumanti.

Ciò che cambia da cantina a cantina **non è nel codice**: sta nei file della cartella del cliente
(`cliente.json`, `vini.csv`, `clienti.csv`), caricati da `cs.customer.package._cs_load`.
Il comando `verticali/cantine/nuovo_cliente.sh` crea l'Odoo dedicato e fa tutto in sequenza:
1. database in italiano;
2. azienda in Italia ed euro prima della contabilità;
3. `l10n_it`;
4. `cantina_standard`;
5. dati del cliente.

I moduli della sezione 1 non compresi nel pacchetto si attivano su richiesta della singola cantina,
come opzioni dell'offerta:
- Punto Vendita, sito ed e-commerce, Email Marketing, Sondaggi, margini;
- DDT;
- i moduli OCA della sezione 2.

| Contenuto | Dove sta | Uguale per tutte le cantine? |
|---|---|---|
| Moduli, listini standard, categorie, impostazioni | `cantina_standard` | Sì |
| Anagrafica vino, ordini da email, schede, Packing List | `langhe_wine_ai` | Sì |
| Azienda, utenti, vini, prezzi, clienti, giacenze iniziali | `clienti/<cantina>/` | No: file del cliente |
| Chiave Claude, posta, cambi | Parametri dell'istanza | No: configurazione del cliente |

---

## 1. Moduli standard Odoo 18 CE

| Area | Moduli tecnici | A cosa servono in cantina |
|---|---|---|
| Vendite | `sale_management` ✅ | Preventivi, ordini, listini, modelli di offerta |
| Magazzino e lotti | `stock`, `sale_stock` ✅ | Giacenze per vino/annata/formato, **lotti di imbottigliamento** (Impostazioni Inventario > *Lotti e numeri di serie*), **confezioni** (*Packagings*: cartone da 6/12, cassa legno) |
| Spedizioni | `stock_delivery` ✅ | Metodi di consegna, peso spedizione, corrieri |
| Acquisti | `purchase` ✅ | Vetro, tappi, capsule, etichette, cartoni, servizi di imbottigliamento conto terzi |
| Fatturazione | `account` ✅ (in CE: *Fatturazione*) | Fatture, note di credito, incassi, scadenzario. La contabilità completa si ottiene con i moduli OCA della sezione 2 |
| Localizzazione | `l10n_it` ✅, `l10n_it_edi` ✅ (fattura elettronica XML FatturaPA), `l10n_it_edi_sale` ✅ | Piano dei conti, IVA, e-fattura |
| DDT | `l10n_it_stock_ddt` ✅ **oppure** OCA `l10n_it_delivery_note` ✅ | Documento di trasporto. **Scegliere uno solo dei due** (vedi nota sotto) |
| CRM | `crm`, `sale_crm` ✅ | Opportunità con importatori, fiere (Vinitaly, ProWein, Wine Paris), campionature |
| Punto vendita | `point_of_sale`, `pos_sale` ✅, `pos_loyalty` ✅ | Vendita diretta in cantina e in sala degustazione, carte fedeltà / wine club |
| Enoturismo | `event`, `event_sale`, `website_event`, `website_event_sale` ✅ | Degustazioni come eventi con biglietti, posti limitati e prenotazione online |
| Sito ed e-commerce (facoltativo) | `website`, `website_sale`, `website_sale_stock` ✅ | Shop online per privati, verifica dell'età da gestire nel tema/checkout |
| Follow-up | `mass_mailing`, `mass_mailing_event`, `mass_mailing_sale` ✅, `survey` ✅, `sms` ✅ | Email post-degustazione, questionari di gradimento, newsletter delle nuove annate |
| Margini | `sale_margin`, `sale_stock_margin` ✅ | Margine per vino, canale e cliente |

**Attenzione: Appuntamenti (`appointment`) è un modulo Enterprise**, quindi non c'è in CE.
In CE le degustazioni si gestiscono come **Eventi**: un evento ricorrente ("Degustazione classica",
"Verticale di Barolo"), con biglietti a pagamento o gratuiti, posti massimi e iscrizione dal sito.
Le visite private si fissano con il **Calendario** (`calendar`).

**DDT, nativo o OCA.** `l10n_it_stock_ddt` (nativo) è più semplice e si integra con l'e-fattura
differita. `l10n_it_delivery_note` (OCA) è più completo: causale, aspetto dei beni, vettore, porto,
DDT raggruppati e DDT senza ordine. Per una cantina che fa export e usa più vettori consiglio l'OCA.
I due moduli sono alternativi, quindi non vanno installati insieme.

---

## 2. Moduli OCA 18.0

### 2.1 Localizzazione italiana (`OCA/l10n-italy`, branch 18.0) ✅

Su 18.0 l'OCA **non** rifà la fattura elettronica da zero come sulle versioni precedenti. Estende
il modulo nativo `l10n_it_edi`.

| Modulo | Funzione |
|---|---|
| `l10n_it_account` | Base contabile italiana comune agli altri moduli OCA |
| `l10n_it_edi_extension` | Estende la FatturaPA nativa (dati mancanti, import fatture passive più completo) |
| `l10n_it_edi_sdi` + `l10n_it_edi_pec` | Canale di invio/ricezione con lo SdI, ad esempio via **PEC**, in alternativa al proxy Odoo. Il canale va deciso con il cliente |
| `l10n_it_edi_related_document` | Riferimenti a ordine/DDT/contratto nell'XML: alcuni distributori Ho.Re.Ca. li richiedono |
| `l10n_it_delivery_note` (+ `l10n_it_delivery_note_order_link`) | DDT completo (vedi sopra) |
| `l10n_it_vat_registries` | Registri IVA |
| `l10n_it_account_vat_period_end_settlement` + `l10n_it_vat_settlement_communication` | Liquidazione IVA periodica e LIPE |
| `l10n_it_central_journal_reportlab` | Libro giornale |
| `l10n_it_financial_statements_report` | Bilancio in formato italiano |
| `l10n_it_riba_oca` + `l10n_it_abicab` | **RiBa**, ancora molto usate con enoteche e ristoranti italiani |
| `l10n_it_account_stamp` | Imposta di bollo sulle fatture non imponibili (export!) |
| `l10n_it_intrastat` + `l10n_it_intrastat_statement` | Elenchi Intrastat per le vendite a clienti UE |
| `l10n_it_currency_rate_update_boi` | Cambi ufficiali Banca d'Italia (fatture in USD, CHF, GBP) |
| `l10n_it_edi_doi_extension` | Dichiarazioni d'intento (esportatori abituali) |
| `l10n_it_fiscalcode_sale`, `l10n_it_pos_fiscalcode` | Codice fiscale dei privati su ordini e POS |

### 2.2 Contabilità, pagamenti, cambi ✅

| Repository | Moduli |
|---|---|
| `account-financial-reporting` | `account_financial_report` (bilancio di verifica, partitari, scadenziario), `partner_statement` (estratto conto cliente) |
| `account-financial-tools` | `account_usability`, `account_fiscal_year`, `account_move_name_sequence` |
| `account-payment` | `account_due_list` (scadenzario), `account_payment_term_extension` (es. 30/60 gg fine mese) |
| `currency` | `currency_rate_update` (aggiornamento automatico dei cambi) |

### 2.3 Prodotto, listini, logistica ✅

| Repository | Moduli | Perché |
|---|---|---|
| `product-attribute` | `product_pricelist_direct_print` (+ `_xlsx`) | **Listini stampabili in PDF/Excel** per cliente o canale, da mandare agli importatori |
| | `product_packaging_level`, `product_packaging_dimension`, `product_total_weight_from_packaging` | Livelli di imballo (bottiglia > cartone > pallet) con misure e pesi |
| | `product_net_weight`, `product_dimension` | Peso netto e dimensioni standard del prodotto |
| | `product_code_unique`, `product_lot_sequence` | Codici univoci e numerazione automatica dei lotti |
| `stock-logistics-workflow` | `stock_picking_auto_create_lot`, `stock_restrict_lot`, `stock_no_negative`, `stock_picking_invoice_link`, `sale_stock_picking_invoice_link` | Lotti in automatico all'imbottigliamento, lotto vincolato sulla riga, niente giacenze negative, legame consegna-fattura |
| `delivery-carrier` | `delivery_carrier_partner` (richiesto dal DDT OCA), `partner_delivery_schedule` | Vettori e orari di consegna dei ristoranti |
| `reporting-engine` | `report_xlsx`, `base_comment_template` | Export Excel; note legali fisse sui documenti (es. dicitura di non imponibilità export) |

### 2.4 Usabilità ✅

`web_responsive` (interfaccia mobile, **indispensabile in CE**), `web_environment_ribbon` (fascia
"PROVA" sull'ambiente di test), `base_location` (CAP e comuni), `partner_firstname`,
`partner_email_check`, `web_dialog_size`.

### 2.5 Da verificare sul branch 18.0 🔎

`OCA/sale-workflow` (es. `sale_triple_discount` per sconto merce + sconto cassa,
`sale_order_line_packaging_qty`), `OCA/pos` (estensioni POS), `OCA/e-commerce`. Questi repository non
sono nel laboratorio: prima di proporli controllare che esistano e siano maturi sul branch 18.0.

### 2.6 Modulo custom

`langhe_wine_ai` (Deliverable 2). Dipende solo da `sale_management`, `sale_stock` e `mail`. Si
installa anche senza la localizzazione, che resta configurazione d'ambiente, e anche senza la
libreria `anthropic`. Senza chiave API lavora in **modalità demo**: regole del modulo, nessuna
chiamata esterna.

`cantina_standard`: pacchetto standard della sezione 0. Dipende da `langhe_wine_ai` e dai moduli
standard sempre presenti.

---

## 3. Struttura dei dati consigliata

### 3.1 Un prodotto per ogni vino + annata + formato

| Scelta | Consigliata? | Motivo |
|---|---|---|
| **Un `product.template` per "Barolo DOCG 2020 0,75 L"** | ✅ Sì | Ogni annata ha prezzo, giacenza, lotti, scheda tecnica e codice SIAN propri. Le annate escono dal listino una alla volta, e la mappatura con il verticale resta 1:1 |
| Varianti con attributo "Annata" | ❌ No | Le varianti condividono descrizione e logica di prezzo. Archiviare un'annata, che ha lotti propri, diventa scomodo |
| Varianti con attributo "Formato" (0,75 / 1,5 / 3 L) | Possibile | Va bene solo se la cantina vende pochi grandi formati e accetta una scheda unica. Di norma meglio prodotti separati |

**Codifica consigliata** (`default_code`): `BAR-20-075`, `BAR-20-150`, `LNB-23-075` (vino, annata,
formato). È leggibile al telefono e la usano Claude e i magazzinieri.

### 3.2 Campi del vino (modulo `langhe_wine_ai`)

| Concetto | Dove | Note |
|---|---|---|
| **Annata** | `lw_vintage` (intero) | 0 = senza annata (NV, spumanti/blend) |
| **Denominazione** | `lw.wine.denomination` (tabella: nome + livello DOCG/DOC/IGT) | Precaricate le principali di Langhe, Roero e Monferrato |
| **Vitigno** | `lw.wine.grape` + % prevalente | Nebbiolo, Barbera, Dolcetto, Arneis... |
| **Grado alcolico** | `lw_alcohol` | Serve anche per i litri anidri |
| **Formato** | `lw_format` (0,375 / 0,75 / 1,5 / 3 / 5 / 6 L) → `lw_volume_l` | Il volume si può correggere a mano |
| **Pesi** | peso netto e lordo bottiglia, tara cartone, misure cartone | Il **peso lordo cartone** e il **volume** si calcolano da soli |

### 3.3 Confezionamento

- **Unità di misura di vendita = bottiglia** (Unità). Fatture, DDT e giacenze sono tutte in bottiglie.
- **Cartone da 6 / da 12 / cassa legno** = *Confezioni* (`product.packaging`) sul prodotto:
  il commerciale scrive "2 cartoni" e Odoo mette 12 bottiglie. Il campo `lw_bottles_per_case` del
  modulo dice a Claude e alla Packing List come convertire.
- Pallet: confezione di livello superiore (es. 100 cartoni) con i moduli OCA `product_packaging_level`.

### 3.4 Lotti

- Tracciabilità **per lotto** su ogni vino (`tracking = lot`). Il lotto si crea all'imbottigliamento,
  con lo stesso codice dell'etichetta, ad esempio `L2420` (anno 24, imbottigliamento n. 20).
- In uscita il lotto si sceglie sulla consegna e compare sul **DDT**: così si risale a quale cliente
  ha ricevuto quale lotto, anche in caso di richiamo.

### 3.5 Listini differenziati

| Listino | Valuta | Regole | Note fiscali |
|---|---|---|---|
| **Privati Cantina** | EUR | Prezzi **IVA inclusa** (prezzo con imposta inclusa sul prodotto o regola di listino). Usato da POS e sito | Corrispettivi da POS / scontrino; registratore telematico da integrare a parte |
| **Ho.Re.Ca. Italia** | EUR | Formula: Privati −X%; prezzi a scaglioni: da 6 bottiglie (1 cartone) e da 60 bottiglie (10 cartoni) | Fattura elettronica, RiBa o bonifico 30/60 gg |
| **Distributori / Importatori UE** | EUR | Prezzi fissi per prodotto, ex-cellar | Posizione fiscale "Cessione intracomunitaria" + Intrastat |
| **Importatori Export Extra-UE (es. USA)** | **USD** | Prezzi fissi in USD per prodotto, Incoterm EXW/FCA/FOB sul preventivo | Posizione fiscale "Esportazione – non imponibile", bollo sulla fattura, Packing List del modulo |

La posizione fiscale e il listino si mettono **sull'anagrafica del cliente**. Da lì arrivano da soli
su ogni preventivo, ed è il listino che il pulsante Claude usa per i prezzi.
Le diciture fiscali e i documenti accise vanno confermati con il commercialista della cantina.
