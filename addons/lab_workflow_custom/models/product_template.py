from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    lab_hours_per_unit = fields.Float(
        "Ore per unità",
        help="Quante ore corrispondono a 1 unità venduta "
             "(es. 'Sviluppo a corpo' = 120h, 'Monte ore 50h' = 50h). "
             "Se vuoto, Odoo usa la conversione standard (1 unità = 1 ora).",
    )
    lab_monthly_hours = fields.Float(
        "Ore mensili incluse",
        help="Per i canoni ricorrenti (AMS): ore incluse ogni mese. "
             "L'alert 75%/90% sul progetto viene calcolato sul mese corrente.",
    )
    lab_create_default_tasks = fields.Boolean(
        "Crea task di gestione interna",
        help="Alla conferma dell'ordine crea anche i task standard "
             "(Analisi e Specifiche, Project Management, Test & UAT) "
             "e distribuisce le ore vendute fra i task.",
    )
