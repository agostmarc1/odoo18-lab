# -*- coding: utf-8 -*-
{
    "name": "Soluzione Cantina – pacchetto standard",
    "version": "18.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Odoo 18 CE pronto per una cantina: moduli, listini, lotti e cartoni, più il caricamento dei dati del cliente",
    "description": """
Pacchetto standard della Software House Lab per le cantine (30.000-150.000 bottiglie/anno).
Uguale per ogni cliente: si installa questo modulo e arrivano da soli vendite, magazzino con
lotti e cartoni, acquisti, CRM, eventi in cantina e il modulo Langhe Wine AI.

Ciò che cambia da una cantina all'altra (anagrafica, vini, prezzi, clienti, utenti) NON sta nel
codice: sta nei file della cartella del cliente (cliente.json, vini.csv, clienti.csv) e si carica
con ``cs.customer.package._cs_load(cartella)``. Il modello dei file è in ``modello_cliente/``.
    """,
    "author": "Software House Lab S.r.l.",
    "license": "LGPL-3",
    "depends": [
        "langhe_wine_ai",     # anagrafica vino, ordini da email, schede, packing list
        "sale_management",
        "sale_stock",
        "purchase",           # bottiglie, tappi, etichette, cartoni dai fornitori
        "crm",                # importatori ed enoteche in trattativa
        "event",              # degustazioni e visite in cantina
        "contacts",
    ],
    "data": [
        "data/product_category_data.xml",
        "data/pricelist_data.xml",
    ],
    "post_init_hook": "_cs_post_init",
    "installable": True,
    "application": True,
}
