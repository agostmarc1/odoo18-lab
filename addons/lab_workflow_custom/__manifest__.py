{
    "name": "Flusso Operativo Software House",
    "summary": "Flusso operativo software house: CRM > Vendite > Progetto > "
               "Pianificazione > Fogli ore > Alert monte ore > Margini > Ticket di assistenza",
    "version": "18.0.1.10.0",
    "category": "Services/Project",
    "description": """
Unica app che contiene TUTTE le personalizzazioni rispetto a Odoo 18 CE standard.
Installandola si attivano da soli i moduli standard e OCA necessari.
Per installarla in un altro Odoo 18: vedi scripts/package_app.sh nel repository odoo18-lab.
""",
    "author": "Marco (odoo18-lab)",
    "license": "LGPL-3",
    "depends": [
        "crm",
        "sale_management",
        "sale_timesheet",
        "project",
        "hr_timesheet",
        "account",
        # OCA, branch 18.0 (inclusi nel pacchetto creato da scripts/package_app.sh)
        "subscription_oca",   # canoni ricorrenti (AMS mensile)
        "project_timeline",   # timeline dei task (porta con sé web_timeline)
        # Ticketing (Helpdesk OCA): ticket, team, stadi, portale, email in arrivo
        "helpdesk_mgmt_timesheet",   # ticket <-> commessa e ore sul ticket (porta helpdesk_mgmt_project)
        "helpdesk_type",             # tipo di richiesta (malfunzionamento, domanda, modifica)
        "helpdesk_mgmt_sla",         # tempi di presa in carico e risoluzione
        "helpdesk_mgmt_rating",      # valutazione del cliente alla chiusura
        "website_helpdesk_mgmt",     # modulo web pubblico "Apri un ticket" (porta il Sito web)
    ],
    "data": [
        "security/lab_security.xml",
        "security/ir.model.access.csv",
        "data/config_data.xml",
        "data/default_task_data.xml",
        "data/product_data.xml",
        "data/cost_data.xml",
        "views/product_views.xml",
        "views/project_views.xml",
        "views/task_views.xml",
        "views/planning_views.xml",
        "views/margin_report_views.xml",
        "views/default_task_views.xml",
        "views/cost_views.xml",
        "views/ai_usage_views.xml",
        "data/helpdesk_data.xml",
        "data/helpdesk_mail_data.xml",
        "data/helpdesk_website_data.xml",
        "views/helpdesk_views.xml",
        "views/portal_templates.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            # modulo pubblico /assistenza: descrizione con formattazione e immagini
            "lab_workflow_custom/static/src/js/helpdesk_rich_description.js",
            "lab_workflow_custom/static/src/scss/helpdesk_rich_description.scss",
            # portale clienti: Kanban dei ticket aggiornato in tempo reale
            "lab_workflow_custom/static/src/js/portal_ticket_kanban.js",
            "lab_workflow_custom/static/src/scss/portal_ticket_kanban.scss",
        ],
    },
    "demo": [
        "demo/demo_users.xml",
        "demo/demo_costs.xml",
        "demo/demo_synthetic.xml",
    ],
    "installable": True,
    "application": True,
}
