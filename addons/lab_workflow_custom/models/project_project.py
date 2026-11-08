from datetime import date

from odoo import _, api, fields, models

from .project_task import ALERT_LEVELS, _alert_level


class ProjectProject(models.Model):
    _inherit = "project.project"

    lab_default_tasks_done = fields.Boolean(copy=False)
    lab_is_monthly = fields.Boolean(
        "Canone mensile", compute="_compute_lab_hours",
        help="Il progetto nasce da un canone mensile (AMS): l'alert usa il mese corrente.")
    lab_sold_hours = fields.Float("Ore vendute", compute="_compute_lab_hours")
    lab_estimated_hours = fields.Float("Ore stimate", compute="_compute_lab_hours")
    lab_consumed_hours = fields.Float("Ore consuntivate", compute="_compute_lab_hours")
    lab_consumption_pct = fields.Float("% consumo ore", compute="_compute_lab_hours")
    lab_alert_level = fields.Selection(ALERT_LEVELS, "Alert monte ore", compute="_compute_lab_hours")
    lab_alert_notified = fields.Selection(
        ALERT_LEVELS, "Ultimo alert notificato", default="none", copy=False)

    def _lab_sale_lines(self):
        self.ensure_one()
        lines = self.sudo().sale_line_id | self.sudo().task_ids.sale_line_id
        return lines.filtered(lambda l: l.project_id == self or l.task_id.project_id == self)

    @api.depends("task_ids.allocated_hours", "task_ids.effective_hours", "sale_line_id")
    def _compute_lab_hours(self):
        AAL = self.env["account.analytic.line"].sudo()
        month_start = date.today().replace(day=1)
        for project in self:
            if not project.id:
                project.update({"lab_is_monthly": False, "lab_sold_hours": 0,
                                "lab_estimated_hours": 0, "lab_consumed_hours": 0,
                                "lab_consumption_pct": 0, "lab_alert_level": "none"})
                continue
            lines = project._lab_sale_lines()
            monthly = lines.filtered(lambda l: l.product_id.lab_monthly_hours)
            domain = [("project_id", "=", project.id)]
            if monthly:
                domain.append(("date", ">=", month_start))
                sold = sum(l.product_id.lab_monthly_hours * l.product_uom_qty for l in monthly)
            else:
                sold = sum(lines.mapped("lab_sold_hours"))
            consumed = sum(AAL.search(domain).mapped("unit_amount"))
            estimated = sum(project.sudo().task_ids.mapped("allocated_hours"))
            pct, level = _alert_level(consumed, sold or estimated)
            project.update({
                "lab_is_monthly": bool(monthly),
                "lab_sold_hours": sold,
                "lab_estimated_hours": estimated,
                "lab_consumed_hours": consumed,
                "lab_consumption_pct": pct,
                "lab_alert_level": level,
            })

    def _lab_check_hours_alert(self):
        """Avvisa PM (attività sul progetto) e Commerciale (attività sull'ordine)
        quando il consumo supera 75% o 90%. Una sola notifica per soglia."""
        rank = {"none": 0, "ok": 1, "warning": 2, "danger": 3}
        for project in self.sudo():
            level = project.lab_alert_level
            if rank[level] <= rank[project.lab_alert_notified]:
                if rank[level] < rank[project.lab_alert_notified]:
                    project.lab_alert_notified = level  # ore stornate: riarma l'alert
                continue
            project.lab_alert_notified = level
            if level not in ("warning", "danger"):
                continue
            threshold = "90%" if level == "danger" else "75%"
            summary = _("Monte ore oltre il %s", threshold)
            note = _("Progetto %(p)s: consuntivate %(c).1fh su %(s).1fh (%(pct).0f%%).",
                     p=project.name, c=project.lab_consumed_hours,
                     s=project.lab_sold_hours or project.lab_estimated_hours,
                     pct=project.lab_consumption_pct)
            project.message_post(body=f"⚠️ {summary}. {note}")
            if project.user_id:
                project.activity_schedule(
                    "mail.mail_activity_data_warning", summary=summary, note=note,
                    user_id=project.user_id.id)
            for order in project._lab_sale_lines().order_id:
                order.message_post(body=f"⚠️ {summary}. {note}")
                if order.user_id:
                    order.activity_schedule(
                        "mail.mail_activity_data_warning", summary=summary, note=note,
                        user_id=order.user_id.id)
