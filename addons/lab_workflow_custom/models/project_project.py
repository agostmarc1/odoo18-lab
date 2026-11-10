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
    lab_contract_type = fields.Selection(
        [("corpo", "A corpo / monte ore prepagato"), ("tm", "A consuntivo (T&M)"),
         ("canone", "Canone ricorrente"), ("interno", "Interno (senza ordine)")],
        "Tipo contratto", compute="_compute_lab_contract_type",
        help="Ricavato dai prodotti venduti. Solo sui contratti T&M le fatture dei consulenti "
             "e le spese vive vengono ribaltate al cliente.")
    lab_passthrough_markup_pct = fields.Float(
        "Ricarico pass-through %",
        default=lambda s: float(s.env["ir.config_parameter"].sudo().get_param(
            "lab_workflow_custom.passthrough_markup_pct", 15)),
        help="Ricarico applicato quando si ribaltano al cliente costi di consulenti esterni e "
             "spese vive (solo contratti T&M). 0 = ribaltamento al puro costo.")
    lab_alert_notified = fields.Selection(
        ALERT_LEVELS, "Ultimo alert notificato", default="none", copy=False)

    # ---- Economia della commessa (dal report margini) ---------------------------
    lab_revenue = fields.Monetary("Ricavi", compute="_compute_lab_economics",
                                  help="Venduto (T&M: ore consegnate × prezzo) + ribaltato al cliente.")
    lab_sold_amount = fields.Monetary("Venduto", compute="_compute_lab_economics")
    lab_passthrough_revenue = fields.Monetary("Ribaltato al cliente",
                                              compute="_compute_lab_economics")
    lab_invoiced_amount = fields.Monetary("Già fatturato", compute="_compute_lab_economics")
    lab_cost_labor = fields.Monetary("Lavoro interno", compute="_compute_lab_economics")
    lab_cost_ai = fields.Monetary("AI", compute="_compute_lab_economics")
    lab_cost_external = fields.Monetary("Consulenti esterni", compute="_compute_lab_economics")
    lab_cost_external_accrued = fields.Monetary("di cui maturato (fattura da ricevere)",
                                                compute="_compute_lab_economics")
    lab_cost_other = fields.Monetary("Altri costi fornitori", compute="_compute_lab_economics")
    lab_total_cost = fields.Monetary("Costi", compute="_compute_lab_economics")
    lab_margin = fields.Monetary("Margine", compute="_compute_lab_economics")
    lab_margin_pct = fields.Float("Margine %", compute="_compute_lab_economics", digits=(5, 1))
    lab_package_line_ids = fields.Many2many(
        "sale.order.line", string="Pacchetti e righe vendute", compute="_compute_lab_packages")

    def _compute_lab_economics(self):
        Report = self.env["lab.margin.report"].sudo()
        ids = [p.id for p in self if isinstance(p.id, int)]
        rows = {r.id: r for r in Report.browse(ids).exists()} if ids else {}
        for project in self:
            r = rows.get(project.id) if isinstance(project.id, int) else None
            if not r:
                project.update({f: 0.0 for f in (
                    "lab_revenue", "lab_sold_amount", "lab_passthrough_revenue",
                    "lab_invoiced_amount", "lab_cost_labor", "lab_cost_ai", "lab_cost_external",
                    "lab_cost_external_accrued", "lab_cost_other", "lab_total_cost",
                    "lab_margin", "lab_margin_pct")})
                continue
            project.update({
                "lab_revenue": r.sold_amount + r.passthrough_revenue,
                "lab_sold_amount": r.sold_amount,
                "lab_passthrough_revenue": r.passthrough_revenue,
                "lab_invoiced_amount": r.invoiced_amount,
                "lab_cost_labor": r.timesheet_cost,
                "lab_cost_ai": r.ai_cost,
                "lab_cost_external": r.external_cost,
                "lab_cost_external_accrued": r.external_accrued,
                "lab_cost_other": r.other_vendor_cost,
                "lab_total_cost": r.total_cost,
                "lab_margin": r.margin,
                "lab_margin_pct": r.margin_pct,
            })

    def _compute_lab_packages(self):
        for project in self:
            lines = project._lab_sale_lines() if isinstance(project.id, int) else False
            project.lab_package_line_ids = lines.filtered("lab_sold_hours") if lines else False

    def _lab_sale_lines(self):
        self.ensure_one()
        lines = self.sudo().sale_line_id | self.sudo().task_ids.sale_line_id
        return lines.filtered(lambda l: l.project_id == self or l.task_id.project_id == self)

    def _lab_contract_type(self):
        self.ensure_one()
        lines = self.sudo()._lab_sale_lines() | self.sudo().sale_order_id.order_line.filtered(
            lambda l: l.is_service and not l.is_expense)
        products = lines.product_id
        if not products:
            return "interno"
        if any(p.lab_monthly_hours for p in products):
            return "canone"
        if any(p.invoice_policy == "delivery" and p.service_type == "timesheet"
               for p in products):
            return "tm"
        return "corpo"

    def _compute_lab_contract_type(self):
        for project in self:
            project.lab_contract_type = project._lab_contract_type() if project.id else "interno"

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
