# Video demo commerciale – 2 minuti

**Pubblico:** produttori delle Langhe, cantine da 30.000 a 150.000 bottiglie.
**Tono:** concreto, da vicino di vigna, niente gergo informatico.
**Formato:** registrazione dello schermo + 2 riprese reali (vigna al tramonto, ufficio di cantina).

### Preparazione dell'ambiente demo
- Si usa l'Odoo dedicato di Cantina Bricco Rosso (http://127.0.0.1:8070, creato da
  `verticali/cantine/nuovo_cliente.sh "Cantina Bricco Rosso"`), che contiene già cliente, listini,
  catalogo, giacenze e il preventivo con l'email di Dave. Si registra con l'utente `elena`.
- Prima di registrare:
  - attivare il Punto Vendita, che è un'opzione del pacchetto, e programmare sull'evento l'email
    "1 giorno dopo";
  - inserire la chiave Claude se si vuole Claude vero. In modalità demo il risultato a schermo è lo
    stesso, ma le note riportano "Modalità demo": in montaggio va tagliata quella riga.
- Cliente *Hudson Fine Wines Import LLC, New York* con listino **Export USA (USD)** e posizione fiscale
  *Esportazione*.
- Catalogo: Barolo 2019 e 2020 (0,75 e Magnum), Barbaresco 2021, Langhe Nebbiolo 2023, Barbera
  d'Alba 2023, Dolcetto d'Alba 2024. Pesi e cartoni compilati, lotti caricati. **Il Magnum 2019 deve
  avere poca giacenza**, così compare l'avviso.
- Evento *Degustazione classica* di sabato scorso con 12 partecipanti ed email di follow-up
  programmata.
- **Tempi:** l'analisi reale richiede in genere 5-20 secondi. In montaggio si taglia l'attesa;
  nel voiceover dire "in pochi secondi" e non promettere "5 secondi".

**Email da incollare (volutamente disordinata):**

> hi Elena!! great to see u at Vinitaly. ok so for our spring program pls send 5 cs of the Barolo
> 2020, also 2 cases nebbiolo (the langhe one) and 6 magnums of barolo 19 if u still have them.
> my partner in Brooklyn asks also for a Barbaresco 2016, do u have?? price for the barolo was
> $31 right? FOB Genova, need it in NY before April 15. cheers, Dave

---

| Tempo | Video / Azioni a schermo | Voiceover (IT) |
|---|---|---|
| **0:00-0:08** | Ripresa reale: vigna al tramonto, il produttore si toglie i guanti. Stacco: scrivania, portatile aperto, la casella di posta conta **15 non lette**. | *"Sono le otto di sera. Sei stato in vigna tutto il giorno. E adesso ti aspettano loro."* |
| **0:08-0:18** | Scorrimento veloce: email in inglese e tedesco ("Bestellung Barolo…", "order for spring…"), un vocale WhatsApp, tre file Excel di listini con nomi diversi (*listino_2024_def.xlsx*, *listino_2024_DEF2.xlsx*). | *"Importatori, enoteche, ristoranti. Ognuno scrive a modo suo, in un'altra lingua, con un altro listino. E le giacenze stanno in un altro file ancora."* |
| **0:18-0:25** | Zoom sull'email di Dave da New York. Titolo in sovrimpressione: **"Quanto tempo ti serve per trasformarla in un ordine?"** | *"Tradurre, controllare annate, prezzi, cartoni, magazzino. Mezz'ora, se va bene. Per ogni email."* |
| **0:25-0:35** | Odoo, Vendite > Nuovo. Scelta del cliente *Hudson Fine Wines*: il listino **Export USA – USD** si compila da solo (evidenziato). | *"Guarda invece come funziona con Odoo e Claude. Scelgo il cliente: il suo listino in dollari è già lì."* |
| **0:35-0:45** | Scheda **Assistente Claude**: incolla l'email di Dave così com'è. Cursore sul pulsante **Analizza Ordine con Claude AI**. Clic. | *"Incollo l'email così com'è, errori compresi. E clicco: Analizza con Claude."* |
| **0:45-0:58** | (Attesa tagliata in montaggio) Le righe compaiono: **Barolo 2020 – 30 bottiglie** (5 cartoni da 6), **Langhe Nebbiolo 2023 – 12**, **Barolo 2019 Magnum – 6**, ognuna con il segno **AI** e il prezzo in USD del listino. Evidenziare "5 cs → 30 bottiglie". | *"In pochi secondi l'ordine è compilato. Ha capito che 'cs' sono cartoni da sei, che 'il nebbiolo' è il Langhe Nebbiolo e che 'barolo 19' è l'annata 2019. I prezzi? Dal listino Export USA, non inventati."* |
| **0:58-1:10** | Scheda Assistente Claude, riquadro **⚠ Da verificare**: "Magnum 2019: giacenza libera 4 bottiglie, richieste 6", "Il cliente cita 31 $ per il Barolo: verificare". Riquadro **✖ Non trovati**: "Barbaresco 2016 – annata non in catalogo". **Consegna**: "FOB Genova, a NY entro il 15 aprile". | *"E soprattutto ti avvisa: il Magnum non basta, mancano due bottiglie. Il Barbaresco 2016 non ce l'hai più. E ha notato il prezzo citato da Dave e la data di consegna."* |
| **1:10-1:15** | Clic su **Conferma**. Lo stato passa a *Ordine di vendita*. | *"Controllo, confermo. Fatto. Due minuti invece di mezz'ora."* |
| **1:15-1:28** | Scheda **Export**: bottiglie, cartoni, colli, litri anidri, peso lordo e m³ già calcolati. Clic su **Packing List**: si apre il PDF bilingue con le colonne pesi. | *"Il container per New York? Pesi, volumi, cartoni e litri anidri sono già calcolati. Un clic e la Packing List è pronta per lo spedizioniere."* |
| **1:28-1:37** | Eventi > *Degustazione classica di sabato*: 12 partecipanti. Scheda Comunicazione: email **"1 giorno dopo l'evento"** già inviata. Anteprima: "Grazie della visita! Ecco il 10% sul primo ordine online". | *"E i turisti passati in cantina sabato? Hanno già ricevuto il grazie con il codice sconto, senza che tu muovessi un dito."* |
| **1:37-1:45** | Punto Vendita sul tablet: scontrino di 3 bottiglie, email del cliente inserita. Le giacenze calano in tempo reale (split screen con il magazzino). | *"Vendita in sala, magazzino ed export: un solo sistema, sempre aggiornato."* |
| **1:45-1:55** | Grafica pulita su sfondo colline: **"Chiavi in mano per la tua cantina"**: ✔ Setup a prezzo fisso, ✔ Nessuna licenza per utente, ✔ Assistenza dedicata qui in Langa, ✔ I tuoi registri SIAN restano dove sono. | *"Lo installiamo noi, chiavi in mano, a prezzo fisso. Nessuna licenza per utente: usatelo in quanti volete. E quando serve, siamo qui in Langa, non in un call center."* |
| **1:55-2:00** | Logo Software House Lab, numero di telefono e QR "Prenota una demo nella tua cantina". | *"Prenota una demo. Veniamo noi da te."* |

---

### Note per chi registra
- **Accuratezza:** "nessuna licenza per utente" è vero per Odoo Community. Restano il canone di
  hosting Cloudpepper e il consumo delle API Claude, fatturato da Anthropic alla cantina. Stima con
  Claude Sonnet 5.5 e un catalogo di 100-300 vini: pochi centesimi per ordine analizzato. Va
  spiegato in trattativa, non nel video.
- Non mostrare la chiave API né la pagina Impostazioni.
- Prima di registrare, provare l'email reale almeno due volte: le risposte possono cambiare nella
  forma. Se il Barbaresco 2016 viene abbinato a un'altra annata con "affidabilità bassa", va bene
  lo stesso: il messaggio della demo è che *avvisa*.
- Sottotitoli in italiano incisi (molti guarderanno il video senza audio su WhatsApp).
