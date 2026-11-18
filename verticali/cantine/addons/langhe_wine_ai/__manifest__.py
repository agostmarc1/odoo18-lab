# -*- coding: utf-8 -*-
{
    "name": "Langhe Wine AI",
    "version": "18.0.1.1.0",
    "category": "Sales/Sales",
    "summary": "Anagrafica vino, ordini da email con Claude, schede tecniche multilingua e packing list export",
    "description": """
Modulo leggero per cantine medio-piccole su Odoo 18 Community:

* anagrafica vino sul prodotto (annata, denominazione, vitigno, grado, formato, pesi e cartone);
* testo grezzo dell'ordine (email, WhatsApp, vocale trascritto) e pulsante
  "Analizza Ordine con Claude AI" che compila le righe dal catalogo e dal listino del cliente;
* scheda tecnica / commerciale IT-EN-DE generata da Claude a partire dai soli dati inseriti;
* riepilogo pesi, volumi e litri anidri dell'ordine e stampa Packing List bilingue.

Senza chiave API lavora in modalità demo (regole del modulo, stesso risultato a schermo).
Non sostituisce i registri telematici SIAN/ICQRF: copre il flusso post-imbottigliamento.
    """,
    "author": "Software House Lab S.r.l.",
    "license": "LGPL-3",
    "depends": [
        "sale_management",
        "sale_stock",
        "mail",
    ],
    # Modalità demo senza chiave API: il modulo si installa e funziona anche senza la libreria
    # 'anthropic'. Per usare Claude vero: pip install anthropic (verificato con 2.9.0; su
    # Cloudpepper nei requirements dell'istanza) e chiave in Impostazioni > Vendite.
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "data/wine_master_data.xml",
        "views/wine_master_views.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
        "report/packing_list_report.xml",
    ],
    "installable": True,
    "application": False,
}
