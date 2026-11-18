# Manuale Cantina – 4 schede rapide

*Per il titolare, l'ufficio commerciale e l'amministrazione. Basta un browser.
I nomi tra virgolette sono quelli che si vedono sullo schermo.*

---

## Guida 1 – Caricare una nuova annata e i lotti imbottigliati

**Quando:** esce una nuova annata, oppure avete appena imbottigliato.

### A. Creare il vino (una volta per annata e formato)
1. Aprite **Vendite > Prodotti > Prodotti** e cercate l'annata precedente, ad esempio *Barolo 2019*.
2. Usate **Azione (⚙) > Duplica**: così ritrovate già denominazione, vitigno, pesi e cartone.
3. Cambiate il **nome** (*Barolo 2020*), il **codice** (*BAR-20-075*) e il **prezzo di vendita**.
4. Nella scheda **Vino** aggiornate:
   - **Annata** (2020) e **Grado alcolico**;
   - **Note del produttore**: affinamento, note di degustazione, abbinamenti. Scrivete con parole
     vostre: l'assistente userà solo quello che c'è qui.
5. Controllate che nella scheda **Inventario** sia attivo il **tracciamento per lotti**.
6. Premete **Genera scheda IT/EN/DE con Claude**. In pochi secondi trovate la scheda tecnica in
   italiano, inglese e tedesco. **Rileggetela sempre** e correggete quello che serve prima di
   mandarla a un cliente.
7. Archiviate l'annata esaurita (**Azione > Archivia**): sparisce dai listini ma lo storico resta.

### B. Registrare un imbottigliamento (lotto)
1. Dal vino, premete il pulsante **In magazzino** e poi **Aggiorna quantità**.
2. Aggiungete una riga: **Ubicazione** = magazzino della cantina, **Lotto** = il codice stampato in
   etichetta (es. *L2420*), **Quantità** = bottiglie imbottigliate. Salvate e applicate.
3. Da quel momento la giacenza è visibile a tutti, all'assistente Claude e al punto vendita.

> 💡 Ogni lotto ha la sua quantità. Quando spedite, Odoo vi chiede da quale lotto prendere le
> bottiglie e lo stampa sul DDT. Così sapete sempre chi ha ricevuto quale lotto.

> ⚠ I registri SIAN restano nel vostro software di cantina. Usate lo **stesso codice lotto** in
> entrambi i programmi.

---

## Guida 2 – Da email o WhatsApp a ordine confermato, in 3 click

**Quando:** un importatore, un'enoteca o un ristorante vi scrive cosa vuole, in qualsiasi lingua.

1. **Vendite > Nuovo** e scegliete il **Cliente**. Il suo listino (es. *Export USA* in dollari) e
   le condizioni fiscali arrivano da soli.
2. Aprite la scheda **Assistente Claude** e **incollate il messaggio così com'è**: email, testo di
   WhatsApp o trascrizione del vocale. Non serve sistemarlo.
3. Premete **Analizza Ordine con Claude AI**.

Dopo qualche secondo:
- nella scheda **Righe ordine** trovate i vini richiesti, con l'annata giusta, le **quantità in
  bottiglie** (i cartoni sono già convertiti) e i **prezzi del listino del cliente**;
- le righe create dall'assistente hanno il segno **AI**;
- nella scheda **Assistente Claude** trovate il riepilogo con:
  - **⚠ Da verificare**: annata dedotta, giacenza insufficiente, prezzo diverso da quello citato dal
    cliente, richieste di sconto o di campioni;
  - **✖ Non trovati in catalogo**: vini o annate che non avete;
  - **Consegna**: date, porto, Incoterm citati nel messaggio.

Controllate i punti ⚠, correggete le righe se serve e premete **Conferma**.

> 💡 Se rilanciate l'analisi, l'assistente sostituisce solo le righe con il segno AI. Le righe
> aggiunte a mano restano.
> 💡 I prezzi non li decide l'assistente: vengono sempre dal listino del cliente in Odoo.
> 💡 Se nelle note leggete *Modalità demo*, Odoo non ha ancora la chiave di Claude. L'analisi
> l'hanno fatta regole semplici: funzionano bene con messaggi chiari ("5 cases Barolo 2020"),
> meno con richieste vaghe. Per Claude vero chiedete all'assistenza di inserire la chiave.

---

## Guida 3 – Degustazioni, vendita in cantina e follow-up ai turisti

> Eventi e degustazioni sono sempre inclusi. Punto Vendita, sito, Email Marketing e Sondaggi sono
> opzioni del pacchetto: se nel menu non li vedete, non sono stati attivati per la vostra cantina.

### A. Preparare le degustazioni
1. **Eventi > Nuovo**: ad esempio *Degustazione classica – sabato ore 11*. Indicate durata, **posti
   massimi** e lingua.
2. Nella scheda **Biglietti** create *Degustazione 3 vini – 20 €* o *Verticale Barolo – 45 €*.
3. Pubblicate l'evento sul sito: i turisti prenotano e pagano online, e voi vedete gli iscritti.
4. Per gruppi o visite private, fissate l'appuntamento nel **Calendario** e collegate un
   preventivo.

### B. Vendere in sala degustazione (Punto Vendita)
1. Aprite **Punto Vendita > Nuova sessione** dal tablet della sala.
2. Toccate i vini, la quantità e il metodo di pagamento (contanti, carta, POS bancario).
3. **Chiedete sempre l'email al cliente** (pulsante *Cliente*): ricevuta digitale e follow-up
   partono da lì.
4. A fine giornata chiudete la sessione: incassi e giacenze sono già aggiornati.

### C. Follow-up automatico
- Su ogni evento, scheda **Comunicazione**, aggiungete l'email **"1 giorno dopo la fine
  dell'evento"**: ringraziamento, link allo shop, codice sconto per il primo ordine online. Parte da
  sola a tutti i partecipanti.
- Per chi ha comprato al banco: **Email Marketing > Nuovo**, destinatari *Contatti* con il filtro
  "ha acquistato al Punto Vendita negli ultimi 7 giorni".
- Un questionario breve (**Sondaggi**) nell'email vi dice cosa è piaciuto di più.

---

## Guida 4 – Proforma, Packing List e DDT per Italia ed export

### Proforma Invoice (per il pagamento anticipato dell'importatore)
1. Dal preventivo: **Invia fattura pro-forma**. Se il pulsante non c'è, va attivata una volta in
   *Vendite > Configurazione > Impostazioni > Fattura pro-forma*.
2. Odoo prepara l'email con il PDF nella lingua del cliente. Controllate e inviate.

### Packing List (pesi e volumi automatici)
1. Sull'ordine aprite la scheda **Export**: bottiglie, cartoni, **colli**, litri, **litri anidri**,
   **peso netto e lordo** e **m³** sono già calcolati.
2. Se compare il riquadro giallo **Dati mancanti**, completate pesi e misure nella scheda Vino di
   quel prodotto. Basta farlo una volta.
3. Premete **Packing List**: esce il PDF bilingue (italiano/inglese) da mandare allo spedizioniere.

### DDT (consegna)
1. Dopo la conferma, aprite il pulsante **Consegna** dell'ordine.
2. Indicate per ogni vino il **lotto** da cui prendete le bottiglie e premete **Convalida**.
3. Stampate il **DDT** dalla consegna: numero, causale, vettore e lotti sono già compilati.

### Fattura
- **Italia:** dall'ordine, **Crea fattura** e poi **Conferma**. La fattura elettronica parte verso
  lo SdI.
- **Export extra-UE:** stessa procedura. Il cliente ha già la posizione fiscale *Esportazione*:
  IVA a zero con la dicitura di legge e marca da bollo se prevista.
- **Clienti UE:** posizione *Cessione intracomunitaria*. Gli importi finiscono da soli negli
  elenchi Intrastat.

> ⚠ I documenti accise (e-DAS / e-AD) si emettono ancora dal software di cantina.
