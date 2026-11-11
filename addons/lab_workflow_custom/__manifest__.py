{
    "name": "Flusso Operativo Software House",
    "summary": "Flusso operativo software house: CRM > Vendite > Progetto > "
               "Pianificazione > Fogli ore > Alert monte ore > Margini",
    "version": "18.0.1.7.2",
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
        "views/menus.xml",
    ],
    "demo": [
        "demo/demo_users.xml",
        "demo/demo_costs.xml",
        "demo/demo_synthetic.xml",
    ],
    "installable": True,
    "application": True,
}
