from odoo import api, fields, models

ALERT_LEVELS = [
    ("none", "Nessun riferimento"),
    ("ok", "Sotto il 75%"),
    ("warning", "Oltre il 75%"),
    ("danger", "Oltre il 90%"),
]


def _alert_level(consumed, reference):
    if not reference:
        return 0.0, "none"
    pct = consumed / reference * 100.0
    if pct >= 90:
        return pct, "danger"
    if pct >= 75:
        return pct, "warning"
    return pct, "ok"


class ProjectTask(models.Model):
    _inherit = "project.task"

    lab_sold_hours = fields.Float(
        "Ore vendute (riga ordine)", related="sale_line_id.lab_sold_hours")
    lab_consumption_pct = fields.Float(
        "% consumo ore", compute="_compute_lab_alert", store=True, aggregator="avg",
        help="Ore consuntivate / Ore stimate (se mancano: ore vendute della riga).")
    lab_alert_level = fields.Selection(
        ALERT_LEVELS, "Alert monte ore", compute="_compute_lab_alert", store=True)

    @api.depends("effective_hours", "allocated_hours", "sale_line_id.lab_sold_hours")
    def _compute_lab_alert(self):
        for task in self:
            reference = task.allocated_hours or task.sale_line_id.lab_sold_hours
            task.lab_consumption_pct, task.lab_alert_level = _alert_level(
                task.effective_hours, reference)
