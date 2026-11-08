from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LabDefaultTask(models.Model):
    """Task standard creati su ogni nuovo progetto venduto (modificabili da UI)."""
    _name = "lab.default.task"
    _description = "Task di default per progetti da ordine"
    _order = "sequence, id"

    name = fields.Char("Nome task", required=True, translate=True)
    sequence = fields.Integer(default=10)
    share_pct = fields.Float(
        "% ore vendute", help="Percentuale delle ore vendute stimata su questo task. "
        "Il task di Sviluppo (quello creato da Odoo) riceve la parte restante.")
    description = fields.Html("Descrizione")
    active = fields.Boolean(default=True)

    @api.constrains("share_pct", "active")
    def _check_total_share(self):
        total = sum(self.search([]).mapped("share_pct"))
        if total >= 100:
            raise ValidationError(
                "La somma delle percentuali dei task di default deve restare sotto il 100% "
                "(la parte restante va allo Sviluppo). Totale attuale: %.0f%%" % total)

    @api.model
    def _create_default_tasks(self, sale_line):
        dev_task = sale_line.task_id
        project = dev_task.project_id
        sold = sale_line.lab_sold_hours
        templates = self.sudo().search([])
        Task = self.env["project.task"].sudo()
        for tmpl in templates:
            Task.create({
                "name": tmpl.name,
                "project_id": project.id,
                "sale_line_id": sale_line.id,
                "partner_id": sale_line.order_id.partner_id.id,
                "allocated_hours": round(sold * tmpl.share_pct / 100.0, 2),
                "description": tmpl.description,
                "sequence": tmpl.sequence,
                "user_ids": False,
            })
        dev_share = 100.0 - sum(templates.mapped("share_pct"))
        dev_task.sudo().write({
            "name": "Sviluppo - %s" % sale_line.product_id.name,
            "allocated_hours": round(sold * dev_share / 100.0, 2),
            "sequence": 50,
        })
        project.sudo().lab_default_tasks_done = True
