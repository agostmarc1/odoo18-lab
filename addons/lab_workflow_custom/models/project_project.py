from datetime import date

from odoo import _, api, fields, models

from .project_task import ALERT_LEVELS, _alert_level


# Chi vede i numeri economici della commessa (ricavi, costi, margini). Il limite è sul campo,
# non solo sulla vista: senza questi gruppi Odoo nega la lettura anche via API.
ECONOMICS_GROUPS = ("lab_workflow_custom.group_lab_pm,lab_workflow_custom.group_lab_amministrazione,"
                    "project.group_project_manager")

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
    lab_revenue = fields.Monetary("Ricavi", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics",
                                  help="Venduto (T&M: ore consegnate × prezzo) + ribaltato al cliente.")
    lab_sold_amount = fields.Monetary("Venduto", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    lab_passthrough_revenue = fields.Monetary("Ribaltato al cliente", groups=ECONOMICS_GROUPS,
                                              compute="_compute_lab_economics")
    lab_invoiced_amount = fields.Monetary("Già fatturato", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    lab_cost_labor = fields.Monetary("Lavoro interno", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    lab_cost_ai = fields.Monetary("AI", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    lab_cost_external = fields.Monetary("Consulenti esterni", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    lab_cost_external_accrued = fields.Monetary("di cui maturato (fattura da ricevere)", groups=ECONOMICS_GROUPS,
                                                compute="_compute_lab_economics")
    lab_cost_other = fields.Monetary("Altri costi fornitori", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    lab_total_cost = fields.Monetary("Costi", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    lab_margin = fields.Monetary("Margine", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    lab_margin_pct = fields.Float("Margine %", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics", digits=(5, 1))
    lab_to_invoice = fields.Monetary("Da fatturare", groups=ECONOMICS_GROUPS, compute="_compute_lab_economics")
    # Panoramica: pulsanti in testa al progetto
    lab_timesheet_count = fields.Integer("Fogli ore", compute="_compute_lab_counts")
    lab_invoice_count = fields.Integer("Fatture", groups=ECONOMICS_GROUPS + ",account.group_account_invoice,account.group_account_readonly", compute="_compute_lab_counts")
    lab_cost_count = fields.Integer("Costi AI e ripartiti", groups=ECONOMICS_GROUPS, compute="_compute_lab_counts")
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
                    "lab_margin", "lab_margin_pct", "lab_to_invoice")})
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
                "lab_to_invoice": max(r.sold_amount + r.passthrough_revenue - r.invoiced_amount,
                                      0.0),
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

    # ---- Panoramica del PM: pulsanti in testa al progetto -----------------------------
    def _lab_invoice_domain(self):
        """Fatture (clienti e fornitori) che riguardano la commessa: righe legate ai suoi
        ordini oppure con la commessa nella distribuzione analitica."""
        self.ensure_one()
        sale_lines = self.env["sale.order.line"].sudo().search([
            "|", "|", ("project_id", "=", self.id), ("task_id.project_id", "=", self.id),
            ("order_id.project_id", "=", self.id)])
        domain = [("move_type", "in", ("out_invoice", "out_refund", "in_invoice", "in_refund"))]
        links = [("invoice_line_ids.sale_line_ids", "in", sale_lines.ids)]
        if self.account_id:
            links = ["|"] + links + [("invoice_line_ids.analytic_distribution", "in",
                                      self.account_id.ids)]
        return domain + links

    def _compute_lab_counts(self):
        AAL = self.env["account.analytic.line"].sudo()
        Move = self.env["account.move"].sudo()
        Alloc = self.env["lab.cost.allocation"].sudo()
        for project in self:
            if not isinstance(project.id, int):
                project.update({"lab_timesheet_count": 0, "lab_invoice_count": 0,
                                "lab_cost_count": 0})
                continue
            project.lab_timesheet_count = AAL.search_count([("project_id", "=", project.id)])
            project.lab_invoice_count = Move.search_count(project._lab_invoice_domain())
            project.lab_cost_count = Alloc.search_count([("project_id", "=", project.id)])

    # ---- Avanzamento del progetto (dai task) --------------------------------
    lab_progress_pct = fields.Float(
        "Avanzamento %", compute="_compute_lab_progress", digits=(5, 1),
        help="Ore registrate sui task stimati / stima a finire di quei task "
             "(ore registrate + ore residue).")
    lab_estimated_task_hours = fields.Float("Tempo stimato task", compute="_compute_lab_progress")
    lab_eac_task_hours = fields.Float("Stima a finire task", compute="_compute_lab_progress")
    lab_forecast_over_count = fields.Integer("Task che sforeranno", compute="_compute_lab_progress")
    lab_effective_task_hours = fields.Float("Tempo effettivo task", compute="_compute_lab_progress")
    lab_late_task_count = fields.Integer("Task in ritardo", compute="_compute_lab_progress")
    lab_to_estimate_count = fields.Integer("Task da stimare", compute="_compute_lab_progress")

    def _compute_lab_progress(self):
        today = fields.Date.context_today(self)
        for project in self:
            tasks = project.sudo().task_ids.filtered(lambda t: t.active)                 if isinstance(project.id, int) else self.env["project.task"]
            estimated = tasks.filtered("allocated_hours")
            project.lab_estimated_task_hours = sum(estimated.mapped("allocated_hours"))
            project.lab_effective_task_hours = sum(estimated.mapped("effective_hours"))
            project.lab_eac_task_hours = sum(estimated.mapped("lab_eac_hours"))
            project.lab_progress_pct = (project.lab_effective_task_hours
                                        / project.lab_eac_task_hours * 100.0
                                        if project.lab_eac_task_hours else 0.0)
            project.lab_forecast_over_count = len(tasks.filtered(
                lambda t: t.lab_forecast_over and not t.is_closed))
            states = [t._lab_schedule_state_on(today) for t in tasks]
            project.lab_late_task_count = sum(s in ("late_start", "late_end") for s in states)
            project.lab_to_estimate_count = states.count("to_estimate")

    def _lab_task_action(self, name, state):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "lab_workflow_custom.action_lab_tasks_to_estimate")
        action.update({"name": name, "domain": [("project_id", "=", self.id),
                                                ("lab_schedule_state", "in", state)],
                       "context": {"default_project_id": self.id}})
        return action

    def action_lab_tasks_late(self):
        return self._lab_task_action(_("Task in ritardo – %s", self.name),
                                     ["late_start", "late_end"])

    def action_lab_tasks_forecast_over(self):
        self.ensure_one()
        action = self._lab_task_action(_("Task che sforeranno – %s", self.name), [])
        action["domain"] = [("project_id", "=", self.id), ("lab_forecast_over", "=", True),
                            ("is_closed", "=", False)]
        return action

    def action_lab_tasks_to_estimate(self):
        return self._lab_task_action(_("Task da stimare – %s", self.name), ["to_estimate"])

    def action_lab_timesheets(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "hr_timesheet.act_hr_timesheet_line")
        action.update({
            "name": _("Fogli ore – %s", self.name),
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id, "search_default_groupby_employee": 1},
        })
        return action

    def action_lab_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "account.move",
            "name": _("Fatture – %s", self.name), "view_mode": "list,form",
            "views": [(self.env.ref("account.view_invoice_tree").id, "list"), (False, "form")],
            "domain": self._lab_invoice_domain(),
            "context": {"create": False},
        }

    def action_lab_costs(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "lab_workflow_custom.action_cost_allocations")
        action.update({"name": _("Costi ripartiti – %s", self.name),
                       "domain": [("project_id", "=", self.id)], "context": {"create": False}})
        return action

    def action_lab_margin(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "lab_workflow_custom.action_margin_report")
        action.update({"domain": [("project_id", "=", self.id)], "context": {},
                       "name": _("Margine – %s", self.name)})
        return action

    # ---- Dashboard di Odoo: pannello "Redditivita'" con i numeri del modulo ------------
    # Il pannello standard conta solo ore e fatture analitiche; qui mostra gli stessi numeri
    # della scheda "Costi, ricavi e margine" (anche AI e consulenti): un solo margine.
    def _get_profitability_labels(self):
        labels = super()._get_profitability_labels()
        labels.update({
            "lab_sold": _("Venduto (ordini)"), "lab_passthrough": _("Ribaltato al cliente"),
            "lab_labor": _("Lavoro interno (fogli ore)"), "lab_ai": _("AI"),
            "lab_external": _("Consulenti esterni"), "lab_other": _("Altri costi fornitori"),
        })
        return labels

    def _get_profitability_sequence_per_invoice_type(self):
        seq = super()._get_profitability_sequence_per_invoice_type()
        seq.update({"lab_sold": 1, "lab_passthrough": 2, "lab_labor": 1, "lab_ai": 2,
                    "lab_external": 3, "lab_other": 4})
        return seq

    def _lab_can_see_economics(self):
        return any(self.env.user.has_group(g) for g in ECONOMICS_GROUPS.split(","))

    def _show_profitability(self):
        # pannello Redditività della Dashboard: solo per chi può vedere i numeri economici
        return super()._show_profitability() and self._lab_can_see_economics()

    def _get_profitability_items(self, with_action=True):
        self.ensure_one()
        p = self
        invoiced_sold = min(p.lab_invoiced_amount, p.lab_sold_amount)
        invoiced_pass = max(p.lab_invoiced_amount - invoiced_sold, 0.0)
        revenues = [
            {"id": "lab_sold", "sequence": 1, "invoiced": invoiced_sold,
             "to_invoice": p.lab_sold_amount - invoiced_sold},
            {"id": "lab_passthrough", "sequence": 2, "invoiced": invoiced_pass,
             "to_invoice": max(p.lab_passthrough_revenue - invoiced_pass, 0.0)},
        ]
        costs = [
            {"id": "lab_labor", "sequence": 1, "billed": -p.lab_cost_labor, "to_bill": 0.0},
            {"id": "lab_ai", "sequence": 2, "billed": -p.lab_cost_ai, "to_bill": 0.0},
            {"id": "lab_external", "sequence": 3,
             "billed": -(p.lab_cost_external - p.lab_cost_external_accrued),
             "to_bill": -p.lab_cost_external_accrued},
            {"id": "lab_other", "sequence": 4, "billed": -p.lab_cost_other, "to_bill": 0.0},
        ]
        revenues = [r for r in revenues if r["invoiced"] or r["to_invoice"]]
        costs = [c for c in costs if c["billed"] or c["to_bill"]]
        return {
            "revenues": {"data": revenues, "total": {
                "invoiced": sum(r["invoiced"] for r in revenues),
                "to_invoice": sum(r["to_invoice"] for r in revenues)}},
            "costs": {"data": costs, "total": {
                "billed": sum(c["billed"] for c in costs),
                "to_bill": sum(c["to_bill"] for c in costs)}},
        }

    # ---- Nomi brevi ---------------------------------------------------------------------
    @api.model
    def _lab_short_names(self):
        """Commesse nate da un ordine: nome breve (riferimento del cliente oppure
        "Cliente – Prodotto") al posto di "Rif - S00005 - [CODICE] Prodotto".
        L'ordine resta visibile nel suo campo e nel pulsante "Ordini di vendita"."""
        # lingue installate più l'inglese (testo di base dei campi traducibili, sempre presente);
        # su un Odoo nuovo l'italiano può mancare
        langs = {"en_US"} | {code for code, _n in self.env["res.lang"].get_installed()}
        for project in self.sudo().with_context(active_test=False).search(
                [("sale_order_id", "!=", False)]):
            order = project.sale_order_id
            names = " ".join(project.with_context(lang=lang).name for lang in langs)
            if order.name not in names:
                continue  # già breve o rinominata a mano
            project._lab_set_name(order._lab_project_name(project.sale_line_id))

    def _lab_set_name(self, name):
        """Stesso nome in tutte le lingue attive (il nome del progetto è traducibile)."""
        langs = [code for code, _n in self.env["res.lang"].get_installed()]
        for project in self:
            project.with_context(mail_notrack=True).name = name
            project.update_field_translations("name", {lang: name for lang in langs})
