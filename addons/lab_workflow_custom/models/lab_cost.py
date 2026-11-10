import calendar
from collections import defaultdict
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

COST_TYPES = [
    ("ai_fixed", "AI - licenze fisse"),
    ("ai_variable", "AI - consumi"),
]


def _month_bounds(day):
    start = day.replace(day=1)
    end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    return start, end


class LabAiTool(models.Model):
    """Catalogo degli strumenti AI (Claude Team/Pro, Claude Code, API...)."""
    _name = "lab.ai.tool"
    _description = "Strumento AI"
    _order = "name"

    name = fields.Char("Strumento", required=True)
    vendor_id = fields.Many2one("res.partner", "Fornitore")
    tool_type = fields.Selection(
        [("license", "Licenza fissa (abbonamento)"), ("usage", "A consumo (API)")],
        "Tipo", required=True, default="license")
    monthly_cost = fields.Monetary("Costo mensile di listino", currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.company.currency_id,
                                  required=True)
    active = fields.Boolean(default=True)


class LabAiLicense(models.Model):
    """Licenza AI assegnata a una persona: si converte in costo per commessa."""
    _name = "lab.ai.license"
    _description = "Licenza AI assegnata"
    _order = "employee_id, date_start desc"

    employee_id = fields.Many2one("hr.employee", "Persona", required=True, index=True,
                                  ondelete="cascade")
    tool_id = fields.Many2one("lab.ai.tool", "Strumento", required=True,
                              domain="[('tool_type', '=', 'license')]")
    monthly_cost = fields.Monetary("Costo mensile", required=True,
                                   currency_field="currency_id")
    currency_id = fields.Many2one(related="tool_id.currency_id")
    date_start = fields.Date("Dal", required=True, default=lambda s: date.today().replace(day=1))
    date_end = fields.Date("Al")
    allocation_mode = fields.Selection(
        [("hours", "In base alle ore della persona"),
         ("governance", "Quota di governance sulle commesse di cui è PM")],
        "Ripartizione", required=True, default="hours",
        help="Ore: il costo va alle commesse in proporzione alle ore che la persona ha "
             "segnato nel mese. Governance (PM/analisti): il costo va alle commesse di cui "
             "la persona è Project Manager, in proporzione alle ore totali della commessa.")

    @api.onchange("tool_id")
    def _onchange_tool_id(self):
        if self.tool_id and not self.monthly_cost:
            self.monthly_cost = self.tool_id.monthly_cost

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for lic in self:
            if lic.date_end and lic.date_end < lic.date_start:
                raise ValidationError(_("La data di fine licenza è prima di quella di inizio."))

    def _is_active_on(self, day):
        self.ensure_one()
        return self.date_start <= day and (not self.date_end or self.date_end >= day)

    def _cost_for_month(self, month_start, month_end):
        """Costo del mese, in proporzione ai giorni di validità della licenza."""
        self.ensure_one()
        start = max(self.date_start, month_start)
        end = min(self.date_end or month_end, month_end)
        if end < start:
            return 0.0
        days_in_month = (month_end - month_start).days + 1
        return self.monthly_cost * ((end - start).days + 1) / days_in_month


class LabCostPeriod(models.Model):
    """Mese di ripartizione dei costi accessori (AI) sulle commesse."""
    _name = "lab.cost.period"
    _description = "Mese di ripartizione costi"
    _order = "date_start desc"

    name = fields.Char("Mese", compute="_compute_name", store=True)
    date_start = fields.Date("Primo giorno", required=True)
    date_end = fields.Date("Ultimo giorno", compute="_compute_name", store=True)
    state = fields.Selection([("open", "Aperto"), ("closed", "Chiuso")], default="open",
                             required=True, string="Stato")
    allocation_ids = fields.One2many("lab.cost.allocation", "period_id", "Ripartizioni")
    total_amount = fields.Monetary("Totale ripartito", compute="_compute_total",
                                   currency_field="currency_id")
    unallocated_amount = fields.Monetary("Costi generali (non attribuiti)",
                                         compute="_compute_total",
                                         currency_field="currency_id")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")

    _sql_constraints = [("month_unique", "unique(date_start, company_id)",
                         "Esiste già questo mese.")]

    @api.depends("date_start")
    def _compute_name(self):
        for period in self:
            if period.date_start:
                period.date_end = _month_bounds(period.date_start)[1]
                period.name = period.date_start.strftime("%m/%Y")
            else:
                period.date_end = False
                period.name = False

    @api.depends("allocation_ids.amount", "allocation_ids.project_id")
    def _compute_total(self):
        for period in self:
            allocs = period.allocation_ids
            period.total_amount = sum(allocs.filtered("project_id").mapped("amount"))
            period.unallocated_amount = sum(
                allocs.filtered(lambda a: not a.project_id).mapped("amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("date_start"):
                vals["date_start"] = _month_bounds(fields.Date.to_date(vals["date_start"]))[0]
        return super().create(vals_list)

    @api.model
    def _get_or_create(self, day):
        start = _month_bounds(day)[0]
        period = self.search([("date_start", "=", start),
                              ("company_id", "=", self.env.company.id)], limit=1)
        return period or self.create({"date_start": start})

    # ---- Calcolo ------------------------------------------------------------
    def action_compute(self):
        for period in self:
            if period.state == "closed":
                raise UserError(_("Il mese %s è chiuso: riaprilo per ricalcolarlo.", period.name))
            period._compute_ai_fixed()
            period._compute_ai_variable()
        return True

    def action_close(self):
        if not (self.env.user.has_group("lab_workflow_custom.group_lab_amministrazione")
                or self.env.user.has_group("base.group_system")):
            raise UserError(_("La chiusura del mese spetta all'Amministrazione."))
        for period in self:
            if period.date_end >= date.today():
                raise UserError(_("Il mese %s non è ancora finito.", period.name))
            period.action_compute()
            period._create_ai_passthrough()
            period.state = "closed"
        return True

    def action_reopen(self):
        if not (self.env.user.has_group("lab_workflow_custom.group_lab_amministrazione")
                or self.env.user.has_group("base.group_system")):
            raise UserError(_("La riapertura del mese spetta all'Amministrazione."))
        for period in self:
            period._remove_ai_passthrough()
        self.write({"state": "open"})
        return True

    def _hours_by_employee_project(self):
        self.ensure_one()
        rows = self.env["account.analytic.line"].sudo()._read_group(
            [("date", ">=", self.date_start), ("date", "<=", self.date_end),
             ("project_id", "!=", False), ("employee_id", "!=", False)],
            ["employee_id", "project_id"], ["unit_amount:sum"])
        hours = defaultdict(dict)
        for employee, project, total in rows:
            hours[employee.id][project.id] = total
        return hours

    def _compute_ai_fixed(self):
        """Licenze fisse -> commesse.
        Mese finito: costo licenza × ore commessa / ore totali della persona (conguaglio esatto).
        Mese in corso: maggiorazione oraria (licenza / ore standard) × ore commessa."""
        self.ensure_one()
        Allocation = self.env["lab.cost.allocation"].sudo()
        Allocation.search([("period_id", "=", self.id), ("cost_type", "=", "ai_fixed")]).unlink()
        finished = self.date_end < date.today()
        std_hours = self.env["hr.employee"]._lab_standard_month_hours()
        hours = self._hours_by_employee_project()
        project_hours = defaultdict(float)
        for per_project in hours.values():
            for project_id, h in per_project.items():
                project_hours[project_id] += h
        licenses = self.env["lab.ai.license"].sudo().search([
            ("date_start", "<=", self.date_end),
            "|", ("date_end", "=", False), ("date_end", ">=", self.date_start),
            ("employee_id.company_id", "in", [self.company_id.id, False]),
        ])
        vals_list = []
        for lic in licenses:
            cost = lic._cost_for_month(self.date_start, self.date_end)
            if not cost:
                continue
            employee = lic.employee_id
            if lic.allocation_mode == "governance":
                managed = self.env["project.project"].sudo().search(
                    [("user_id", "=", employee.user_id.id)]) if employee.user_id else []
                weights = {p.id: project_hours[p.id] for p in managed if project_hours.get(p.id)}
                basis = _("governance: ore totali delle commesse di cui è PM")
            else:
                weights = dict(hours.get(employee.id, {}))
                basis = _("ore della persona nel mese")
            total = sum(weights.values())
            common = {"period_id": self.id, "cost_type": "ai_fixed", "employee_id": employee.id,
                      "license_id": lic.id}
            if not total:
                vals_list.append(dict(common, amount=cost, basis=_(
                    "nessuna ora nel mese: costi generali")))
                continue
            for project_id, weight in weights.items():
                share = weight / total
                if finished or lic.allocation_mode == "governance":
                    amount = cost * share
                else:
                    amount = min(cost * share, cost / std_hours * weight) if std_hours else 0.0
                vals_list.append(dict(common, project_id=project_id, amount=amount,
                                      basis_qty=weight, basis_pct=share * 100, basis=basis))
            if not finished and lic.allocation_mode == "hours" and std_hours:
                absorbed = sum(v["amount"] for v in vals_list
                               if v.get("license_id") == lic.id and v.get("project_id"))
                if cost - absorbed > 0.005:
                    vals_list.append(dict(common, amount=cost - absorbed, basis=_(
                        "mese in corso: quota non ancora assorbita dalle ore")))
        Allocation.create(vals_list)

    def _compute_ai_variable(self):
        """Consumi AI (API, Claude Code) -> commesse.
        Diretto (workspace/chiave della commessa): tutto sulla commessa.
        Per persona: ripartito sulle ore della persona nel mese. Altrimenti: costi generali."""
        self.ensure_one()
        Allocation = self.env["lab.cost.allocation"].sudo()
        Allocation.search([("period_id", "=", self.id),
                           ("cost_type", "=", "ai_variable")]).unlink()
        usages = self.env["lab.ai.usage"].sudo().search([
            ("date", ">=", self.date_start), ("date", "<=", self.date_end),
            ("company_id", "=", self.company_id.id)])
        hours = self._hours_by_employee_project()
        direct = defaultdict(float)
        by_person = defaultdict(float)
        overhead = 0.0
        for usage in usages:
            if usage.attribution == "direct":
                direct[usage.project_id.id] += usage.amount
            elif usage.attribution == "person":
                by_person[usage.employee_id.id] += usage.amount
            else:
                overhead += usage.amount
        vals_list = []
        for project_id, amount in direct.items():
            project = self.env["project.project"].sudo().browse(project_id)
            vals_list.append({
                "period_id": self.id, "cost_type": "ai_variable", "project_id": project_id,
                "amount": amount, "basis_pct": 100,
                "basis": _("consumi del workspace/chiave dedicati alla commessa"),
                "passthrough": project._lab_contract_type() == "tm"})
        for employee_id, amount in by_person.items():
            weights = hours.get(employee_id, {})
            total = sum(weights.values())
            if not total:
                vals_list.append({"period_id": self.id, "cost_type": "ai_variable",
                                  "employee_id": employee_id, "amount": amount,
                                  "basis": _("nessuna ora nel mese: costi generali")})
                continue
            for project_id, weight in weights.items():
                vals_list.append({
                    "period_id": self.id, "cost_type": "ai_variable", "project_id": project_id,
                    "employee_id": employee_id, "amount": amount * weight / total,
                    "basis_qty": weight, "basis_pct": weight / total * 100,
                    "basis": _("consumi personali ripartiti sulle ore del mese")})
        if overhead:
            vals_list.append({"period_id": self.id, "cost_type": "ai_variable",
                              "amount": overhead,
                              "basis": _("consumi senza corrispondenza: costi generali")})
        Allocation.create(vals_list)

    def _passthrough_label(self):
        return _("Spese vive AI %s", self.name)

    def _create_ai_passthrough(self):
        """Mese chiuso: i consumi dedicati alle commesse T&M diventano spese vive
        sull'ordine del cliente (costo + ricarico), pronte da fatturare."""
        self.ensure_one()
        product = self.env.ref(
            "lab_workflow_custom.product_passthrough_expense").product_variant_id
        allocations = self.allocation_ids.filtered(
            lambda a: a.passthrough and a.project_id and not a.sale_line_id)
        for project in allocations.project_id:
            project = project.sudo()
            order = self.env["sale.order"].sudo().search(
                [("project_id", "=", project.id), ("state", "=", "sale")],
                order="create_date", limit=1) or project.sale_order_id
            if not order or order.locked:
                continue
            allocs = allocations.filtered(lambda a: a.project_id == project)
            cost = sum(allocs.mapped("amount"))
            markup = project.lab_passthrough_markup_pct or 0.0
            label = self._passthrough_label()
            price = order.currency_id.round(cost * (1 + markup / 100.0))
            line = order.order_line.filtered(lambda l: l.is_expense and l.name == label)[:1]
            if line:
                line.write({"price_unit": price, "product_uom_qty": 1})
            else:
                line = self.env["sale.order.line"].sudo().create({
                    "order_id": order.id, "product_id": product.id, "name": label,
                    "product_uom_qty": 1, "price_unit": price, "is_expense": True,
                    "tax_id": [(6, 0, [])]})
            # la riga analitica fa risultare la spesa "consegnata", quindi fatturabile
            self.env["account.analytic.line"].sudo().create({
                "name": label, "date": self.date_end, "account_id": project.account_id.id,
                "amount": -cost, "unit_amount": 1, "product_id": product.id,
                "product_uom_id": product.uom_id.id, "so_line": line.id,
                "company_id": self.company_id.id})
            allocs.write({"sale_line_id": line.id})

    def _remove_ai_passthrough(self):
        self.ensure_one()
        lines = self.allocation_ids.sale_line_id
        if any(line.qty_invoiced for line in lines):
            raise UserError(_("Le spese vive AI del mese %s sono già state fatturate al "
                              "cliente: non si può riaprire il mese.", self.name))
        label = self._passthrough_label()
        self.env["account.analytic.line"].sudo().search(
            [("so_line", "in", lines.ids), ("name", "=", label)]).unlink()
        self.allocation_ids.write({"sale_line_id": False})

    @api.model
    def _cron_compute_open_periods(self):
        """Ogni notte: ricalcola il mese in corso e quello precedente se ancora aperto."""
        today = date.today()
        previous = today.replace(day=1) - timedelta(days=1)
        for day in (previous, today):
            period = self._get_or_create(day)
            if period.state == "open":
                period._compute_ai_fixed()
                period._compute_ai_variable()


class LabCostAllocation(models.Model):
    """Registro delle ripartizioni: da qui legge il report Margini per commessa."""
    _name = "lab.cost.allocation"
    _description = "Ripartizione costo su commessa"
    _order = "period_id desc, project_id, employee_id"

    period_id = fields.Many2one("lab.cost.period", "Mese", required=True, ondelete="cascade",
                                index=True)
    date = fields.Date(related="period_id.date_start", store=True, string="Data")
    project_id = fields.Many2one("project.project", "Commessa", index=True,
                                 help="Vuoto = costi generali, non attribuiti a una commessa.")
    employee_id = fields.Many2one("hr.employee", "Persona")
    license_id = fields.Many2one("lab.ai.license", "Licenza", ondelete="set null")
    cost_type = fields.Selection(COST_TYPES, "Tipo costo", required=True)
    passthrough = fields.Boolean(
        "Da ribaltare", help="Consumo dedicato a una commessa T&M: alla chiusura del mese "
                             "diventa una spesa viva sull'ordine del cliente.")
    sale_line_id = fields.Many2one("sale.order.line", "Ribaltato su", readonly=True,
                                   ondelete="set null")
    amount = fields.Monetary("Importo", currency_field="currency_id")
    basis = fields.Char("Base di calcolo")
    basis_qty = fields.Float("Ore base")
    basis_pct = fields.Float("% attribuita", digits=(5, 2))
    company_id = fields.Many2one(related="period_id.company_id", store=True)
    currency_id = fields.Many2one(related="period_id.currency_id")


class LabPlanningCapacity(models.Model):
    """Correzione settimanale del fattore parallelo di una persona (la decide il PM)."""
    _name = "lab.planning.capacity"
    _description = "Fattore parallelo settimanale"
    _order = "week_start desc, employee_id"

    employee_id = fields.Many2one("hr.employee", "Persona", required=True, ondelete="cascade")
    week_start = fields.Date("Settimana (lunedì)", required=True)
    parallel_factor = fields.Float("Fattore parallelo", required=True, default=1.0)
    note = fields.Char("Motivo")

    _sql_constraints = [("week_unique", "unique(employee_id, week_start)",
                         "Per questa persona la settimana è già impostata.")]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("week_start"):
                day = fields.Date.to_date(vals["week_start"])
                vals["week_start"] = day - timedelta(days=day.weekday())
        return super().create(vals_list)

    @api.constrains("parallel_factor")
    def _check_factor(self):
        for cap in self:
            if not 0.1 <= cap.parallel_factor <= 3:
                raise ValidationError(_("Il fattore parallelo deve essere tra 0,1 e 3."))
