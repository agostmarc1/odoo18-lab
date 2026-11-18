# -*- coding: utf-8 -*-
"""Modalità demo: analisi dell'ordine e scheda tecnica SENZA chiamare Claude.

Serve per dimostrazioni, formazione e ambienti di prova senza chiave API.
Le regole sono semplici e prevedibili (parole chiave, numeri, annate): non hanno
la flessibilità di Claude, ma restituiscono lo STESSO formato di risposta
(``ORDER_SCHEMA`` / ``SHEET_SCHEMA``), così il resto del modulo funziona uguale.
"""
import re
import unicodedata

UNIT_CASES = r"cs|cases?|cartons?|cartoni|cartone|casse|cassa|kisten?|kartons?|ctn"
UNIT_BOTTLES = r"bottles?|btls?|bt|bottiglie|bottiglia|flaschen|flasche|magnums?|mg"
SPLIT_RE = re.compile(
    r"[\n;!?]+|\.(?!\d)|,(?!\d)|\b(?:and|also|plus|und|sowie|auch|e|ed|poi|inoltre|anche)\b")
QTY_RE = re.compile(r"(?<![\$€\d.,])\b(\d{1,3})\s*(?:x\s*)?(%s|%s)\b" % (UNIT_CASES, UNIT_BOTTLES))
QTY_BEFORE_WINE_RE = r"(?<![\$€\d.,])\b(\d{1,3})\s+(?:x\s+)?(?:of\s+|di\s+|del\s+|von\s+)?(?:the\s+|il\s+|lo\s+)?%s"
ARTICLE_RE = r"\b(?:a|an|one|una|un|uno|ein|eine|einen)\s+(?:bottle of\s+|bottiglia di\s+)?%s"
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
SHORT_YEAR_RE = re.compile(r"['’](\d{2})\b")
PRICE_RE = re.compile(
    r"(?:[\$€]\s?\d+(?:[.,]\d+)?|\b\d+(?:[.,]\d+)?\s?(?:\$|€|usd|eur|euro)\b)", re.I)
INCOTERM_RE = re.compile(r"\b(?:exw|fca|fob|cif|cfr|cpt|cip|dap|dpu|ddp)\b", re.I)
DELIVERY_WORDS = re.compile(
    r"\b(?:deliver\w*|ship\w*|need it|before|by the end|consegn\w*|spedi\w*|entro|"
    r"liefer\w*|versand|bis zum|bis ende)\b", re.I)
SPECIAL_WORDS = re.compile(
    r"\b(?:discount|sconto|rabatt|samples?|campion\w*|muster|promo\w*|gratis|free of charge)\b", re.I)
STOPWORDS = {"del", "di", "d", "della", "dei", "the", "doc", "docg", "igt", "vino"}
LANG_WORDS = {
    "en": {"the", "and", "please", "pls", "send", "cases", "bottles", "need", "thanks", "cheers",
           "hi", "hello", "order", "u", "you", "for", "our"},
    "de": {"bitte", "und", "kisten", "flaschen", "wir", "liefern", "danke", "grüße", "gruesse",
           "hallo", "bestellung", "für", "möchten"},
    "it": {"ciao", "grazie", "bottiglie", "casse", "cartoni", "per", "vorrei", "mandare", "buongiorno",
           "ordine", "saluti", "il", "di"},
}


def _norm(text):
    """Minuscolo, apostrofi uniformi, accenti tolti solo per il confronto."""
    text = (text or "").lower().replace("’", "'")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _tokens(text):
    return [t for t in re.split(r"[^a-z0-9]+", _norm(text)) if len(t) >= 3 and t not in STOPWORDS]


def _vintage_in(segment, wine_tokens):
    match = YEAR_RE.search(segment)
    if match:
        return int(match.group(1))
    match = SHORT_YEAR_RE.search(segment)
    if not match:
        for token in wine_tokens:
            match = re.search(r"\b%s\s+(\d{2})\b(?!\s*(?:%s|%s))" % (re.escape(token), UNIT_CASES, UNIT_BOTTLES),
                              segment)
            if match:
                break
    if match:
        short = int(match.group(1))
        return 2000 + short if short <= 49 else 1900 + short
    return None


def _language(text):
    words = set(re.split(r"[^a-zà-ÿß]+", (text or "").lower()))
    scores = {lang: len(words & vocab) for lang, vocab in LANG_WORDS.items()}
    lang = max(scores, key=scores.get)
    return lang if scores[lang] else "it"


def analyze_order(text, catalog):
    """Restituisce un dict conforme a ORDER_SCHEMA.

    ``catalog``: elenco di dict come ``sale.order._lw_catalog`` più le chiavi interne
    ``_den`` (nome denominazione senza livello), ``_name_tokens`` (parole del nome).
    """
    wines = [c for c in catalog if c.get("_den")]
    den_tokens = {c["id"]: set(_tokens(c["_den"])) for c in wines}
    known_tokens = set().union(*den_tokens.values()) if den_tokens else set()
    for c in wines:
        known_tokens |= set(c.get("_name_tokens") or ())

    lines, unmatched, doubts = [], [], []
    for raw in SPLIT_RE.split(text or ""):
        if not raw or not raw.strip():
            continue
        seg = _norm(raw).strip()
        seg_tokens = set(_tokens(seg))
        if not seg_tokens & known_tokens:
            continue
        # 1) quale vino: conta le parole della denominazione (e del nome) presenti
        scored = []
        for c in wines:
            den_hit = len(den_tokens[c["id"]] & seg_tokens)
            name_hit = len(set(c.get("_name_tokens") or ()) & seg_tokens)
            if den_hit or name_hit:
                scored.append((den_hit * 2 + name_hit * 3 - len(den_tokens[c["id"]] - seg_tokens), c))
        if not scored:
            continue
        best_score = max(s for s, _c in scored)
        candidates = [c for s, c in scored if s == best_score]
        wine_words = sorted(seg_tokens & known_tokens)

        # 2) quantità e unità
        unit, qty = None, None
        match = QTY_RE.search(seg)
        if match:
            qty = int(match.group(1))
            unit = "casse" if re.fullmatch(UNIT_CASES, match.group(2)) else "bottiglie"
        else:
            for word in wine_words:
                m = re.search(QTY_BEFORE_WINE_RE % re.escape(word), seg)
                if m:
                    qty, unit = int(m.group(1)), "bottiglie"
                    break
            if qty is None and any(re.search(ARTICLE_RE % re.escape(w), seg) for w in wine_words):
                qty, unit = 1, "bottiglie"
        if qty is None:
            continue  # parla di un vino ma non lo ordina (es. "il prezzo del barolo era 31 $")

        # 3) formato e annata
        magnum = bool(re.search(r"\bmagnum", seg)) or "1,5" in seg or "1.5" in seg
        wanted_l = 1.5 if magnum else 0.75
        in_format = [c for c in candidates if abs(float(c.get("formato_l") or 0.75) - wanted_l) < 0.01]
        vintage = _vintage_in(seg, wine_words)
        requested = raw.strip()
        notes, confidence = [], "alta"
        if not in_format:
            unmatched.append({"requested_text": requested,
                              "reason": "formato %s L non presente per %s" % (
                                  str(wanted_l).replace(".", ","), candidates[0]["_den"])})
            continue
        if vintage:
            exact = [c for c in in_format if str(c.get("annata")) == str(vintage)]
            if not exact:
                available = sorted({str(c.get("annata")) for c in in_format})
                unmatched.append({"requested_text": requested,
                                  "reason": "annata %s non in catalogo (disponibili: %s)" % (
                                      vintage, ", ".join(available))})
                continue
            chosen = exact
        else:
            chosen = in_format
            if len({c.get("annata") for c in in_format}) > 1:
                confidence = "media"
        if len(candidates) > 1 and len({c["_den"] for c in candidates}) > 1:
            confidence = "media"
            notes.append("più denominazioni possibili (%s)" % ", ".join(sorted({c["_den"] for c in candidates})))
        # a parità: prima chi ha giacenza, poi l'annata più recente
        product = sorted(chosen, key=lambda c: ((c.get("giacenza_libera") or 0) > 0,
                                                str(c.get("annata"))), reverse=True)[0]
        if not vintage and product.get("annata") and confidence == "media":
            notes.append("annata non indicata: proposta la %s" % product["annata"])
        lines.append({
            "product_id": product["id"],
            "requested_text": requested,
            "quantity": qty,
            "unit": unit,
            "confidence": confidence,
            "note": "; ".join(notes),
        })

    # prezzi citati, richieste speciali, consegna (frase per frase sul testo originale)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text or "") if s.strip()]
    for sentence in sentences:
        if PRICE_RE.search(sentence):
            doubts.append("Il cliente cita un prezzo: «%s». Verificare con il listino." % sentence.strip())
        if SPECIAL_WORDS.search(sentence):
            doubts.append("Richiesta particolare (sconto, campioni o promozioni): «%s»." % sentence.strip())
    delivery = [s for s in sentences if INCOTERM_RE.search(s) or DELIVERY_WORDS.search(s)]

    summary = "Vini abbinati al catalogo: %d" % len(lines)
    if unmatched:
        summary += "; richieste non trovate: %d" % len(unmatched)
    summary += "."
    return {
        "customer_language": _language(text),
        "lines": lines,
        "unmatched": unmatched,
        "doubts": doubts,
        "delivery_notes": " ".join(delivery),
        "summary": summary,
    }


SHEET_LABELS = {
    "it": {"intro": "Vino della nostra cantina nelle Langhe.", "tech": "Dati tecnici",
           "den": "Denominazione", "vintage": "Annata", "grape": "Vitigno", "alcohol": "Gradazione",
           "format": "Formato", "case": "Cartone", "bottles": "bottiglie", "notes": "Note del produttore",
           "nv": "senza annata"},
    "en": {"intro": "A wine from our estate in the Langhe hills.", "tech": "Technical data",
           "den": "Appellation", "vintage": "Vintage", "grape": "Grape", "alcohol": "Alcohol",
           "format": "Bottle size", "case": "Case", "bottles": "bottles", "notes": "Producer's notes",
           "nv": "non vintage"},
    "de": {"intro": "Ein Wein aus unserem Weingut in den Langhe.", "tech": "Technische Daten",
           "den": "Herkunftsbezeichnung", "vintage": "Jahrgang", "grape": "Rebsorte",
           "alcohol": "Alkoholgehalt", "format": "Flaschengröße", "case": "Karton", "bottles": "Flaschen",
           "notes": "Anmerkungen des Erzeugers", "nv": "ohne Jahrgang"},
}


def technical_sheet(facts):
    """Scheda IT/EN/DE dai soli dati inseriti (nessun testo inventato)."""
    result = {}
    for lang, lab in SHEET_LABELS.items():
        vintage = facts.get("annata")
        vintage = vintage if isinstance(vintage, int) else lab["nv"]
        title = " ".join(str(x) for x in (facts.get("denominazione") or facts.get("nome"), vintage) if x)
        rows = [
            (lab["den"], facts.get("denominazione")),
            (lab["vintage"], vintage),
            (lab["grape"], facts.get("vitigno")),
            (lab["alcohol"], "%s%% vol" % facts["gradazione_vol"] if facts.get("gradazione_vol") else ""),
            (lab["format"], "%s L" % str(facts["formato_litri"]).replace(".", ",") if facts.get("formato_litri") else ""),
            (lab["case"], "%s %s" % (facts["bottiglie_per_cartone"], lab["bottles"])
             if facts.get("bottiglie_per_cartone") else ""),
        ]
        body = [title, "", lab["intro"], "", lab["tech"] + ":"]
        body += ["- %s: %s" % (label, value) for label, value in rows if value]
        if facts.get("note_produttore"):
            body += ["", lab["notes"] + ":", facts["note_produttore"]]
        result[lang] = "\n".join(body)
    return result
