from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

DEFAULT_DAY_HOURS = 8.0

PARALLEL_STATES = [
    ("normal", "Giornata normale"),
    ("to_approve", "Ore parallele da approvare"),
    ("approved", "Ore parallele approvate"),
]


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    # ---- Lavoro in parallelo (più commesse nella stessa giornata) ---------
    lab_parallel_ratio = fields.Float(
        "Fattore giornata", default=1.0, readonly=True, copy=False, digits=(4, 3),
        help="Ore del calendario / ore segnate nel giorno (massimo 1). Se la persona segna "
             "più ore di quelle della sua giornata, il costo si divide tra le commesse "
             "invece di raddoppiare.")
    lab_parallel_state = fields.Selection(
        PARALLEL_STATES, "Ore parallele", default="normal", readonly=True, copy=False,
        index=True,
        help="Se nel giorno la persona supera le ore del suo calendario, le ore restano "
             "fatturabili ma vanno approvate dal PM prima della fattura (contratti T&M).")
    lab_resource_type = fields.Selection(related="employee_id.lab_resource_type",
                                         string="Tipo risorsa")
    # ---- Consulenti esterni ------------------------------------------------
    lab_accrued_external_cost = fields.Monetary(
        "Costo maturato consulente", readonly=True, copy=False,
        currency_field="currency_id",
        help="Ore × tariffa concordata del consulente. Vale finché non arriva la sua fattura.")
    lab_vendor_bill_line_id = fields.Many2one(
        "account.move.line", "Fattura consulente", readonly=True, copy=False, index=True,
        ondelete="set null")

    # ---- Tracciabilità: sulle commesse vendute a ore ogni foglio ore ha un task --
    @api.constrains("project_id", "task_id")
    def _check_lab_task_required(self):
        if self.env.context.get("install_mode"):
            return
        for line in self.filtered(lambda l: l.project_id and not l.task_id):
            if line.sudo().project_id._lab_contract_type() in ("corpo", "tm"):
                if line.ticket_id:
                    raise ValidationError(_(
                        "Il ticket %(t)s è sulla commessa %(p)s, venduta a ore: prima di segnare "
                        "le ore collega il ticket a un task della commessa (campo Task).",
                        t=line.ticket_id.display_name, p=line.project_id.display_name))
                raise ValidationError(_(
                    "Sul progetto %s indica il task: le ore scalate dal pacchetto o fatturate "
                    "al cliente devono dire su quale attività sono state spese.",
                    line.project_id.display_name))

    # ---- Costo orario -------------------------------------------------------
    def _hourly_cost(self):
        # I consulenti esterni non hanno costo "da dipendente": il loro costo arriva dalla
        # fattura (e, finché manca, dal costo maturato). Così non si conta due volte.
        if self.employee_id.lab_resource_type == "external":
            return 0.0
        return super()._hourly_cost()

    def _timesheet_determine_sale_line(self):
        # Contratti T&M: le ore dei consulenti esterni NON si fatturano a tariffa oraria,
        # perché al cliente si ribalta la loro fattura (pass-through). Così non si fattura due volte.
        if (self.sudo().employee_id.lab_resource_type == "external"
                and self.project_id and self.project_id._lab_contract_type() == "tm"):
            return self.env["sale.order.line"]
        return super()._timesheet_determine_sale_line()

    # ---- Hook su create / write / unlink ------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        # Ore segnate su un ticket: commessa e task arrivano dal ticket (anche fuori dal modulo,
        # dove l'onchange di OCA non scatta)
        for vals in vals_list:
            if not vals.get("ticket_id"):
                continue
            ticket = self.env["helpdesk.ticket"].sudo().browse(vals["ticket_id"])
            if not vals.get("project_id") and ticket.project_id:
                vals["project_id"] = ticket.project_id.id
            if (not vals.get("task_id") and ticket.task_id
                    and ticket.task_id.project_id.id == vals.get("project_id")):
                vals["task_id"] = ticket.task_id.id
        lines = super().create(vals_list)
        if not self.env.context.get("lab_skip_parallel"):
            lines._lab_recompute_days(lines._lab_day_keys())
        lines.project_id._lab_check_hours_alert()
        return lines

    def write(self, vals):
        if self.env.context.get("lab_skip_parallel"):
            return super().write(vals)
        projects = self.project_id
        keys = self._lab_day_keys()
        res = super().write(vals)
        if {"unit_amount", "employee_id", "date", "project_id", "account_id"} & set(vals):
            self._lab_recompute_days(keys | self._lab_day_keys())
        (projects | self.project_id)._lab_check_hours_alert()
        return res

    def unlink(self):
        projects = self.project_id
        keys = self._lab_day_keys()
        res = super().unlink()
        self._lab_recompute_days(keys)
        projects.exists()._lab_check_hours_alert()
        return res

    # ---- Calcolo per persona e giorno ----------------------------------------
    def _lab_day_keys(self):
        return {(line.employee_id.id, line.date) for line in self
                if line.project_id and line.employee_id and line.date}

    @api.model
    def _lab_day_hours(self, employee):
        return employee.resource_calendar_id.hours_per_day or DEFAULT_DAY_HOURS

    @api.model
    def _lab_recompute_days(self, keys):
        """Per ogni (persona, giorno): fattore = ore calendario / ore segnate (max 1).
        Il costo di ogni riga = ore × costo orario × fattore. Le ore NON cambiano."""
        if not keys:
            return
        by_employee = defaultdict(set)
        for employee_id, day in keys:
            by_employee[employee_id].add(day)
        AAL = self.sudo().with_context(lab_skip_parallel=True)
        for employee_id, days in by_employee.items():
            employee = self.env["hr.employee"].sudo().browse(employee_id)
            day_hours = self._lab_day_hours(employee)
            lines = AAL.search([("employee_id", "=", employee_id), ("date", "in", list(days)),
                                ("project_id", "!=", False)])
            per_day = defaultdict(lambda: AAL.browse())
            for line in lines:
                per_day[line.date] |= line
            for day_lines in per_day.values():
                total = sum(day_lines.mapped("unit_amount"))
                ratio = min(1.0, day_hours / total) if total > 0 else 1.0
                over = total > day_hours + 1e-6
                for line in day_lines:
                    vals = {}
                    if abs(line.lab_parallel_ratio - ratio) > 1e-6:
                        vals["lab_parallel_ratio"] = ratio
                    state = line.lab_parallel_state
                    if not over:
                        state = "normal"
                    elif state == "normal":
                        state = "to_approve"
                    if state != line.lab_parallel_state:
                        vals["lab_parallel_state"] = state
                    cost = -line.unit_amount * line._hourly_cost() * ratio
                    amount = line.employee_id.currency_id._convert(
                        cost, line.account_id.currency_id or line.currency_id,
                        line.company_id or self.env.company, line.date)
                    if line.currency_id.compare_amounts(amount, line.amount):
                        vals["amount"] = amount
                    accrued = (line.unit_amount * ratio * employee._lab_external_hourly_rate()
                               if employee.lab_resource_type == "external" else 0.0)
                    if line.currency_id.compare_amounts(accrued, line.lab_accrued_external_cost):
                        vals["lab_accrued_external_cost"] = accrued
                    if vals:
                        line.write(vals)
            # le ore da approvare non vanno in fattura: ricalcola il consegnato T&M
            lines.so_line._lab_refresh_delivered()

    # ---- Approvazione del PM -------------------------------------------------
    def action_lab_approve_parallel(self):
        if not (self.env.user.has_group("lab_workflow_custom.group_lab_pm")
                or self.env.user.has_group("project.group_project_manager")):
            raise AccessError(_("Solo il Project Manager può approvare le ore parallele."))
        lines = self.sudo().filtered(lambda l: l.lab_parallel_state == "to_approve")
        lines.with_context(lab_skip_parallel=True).write({"lab_parallel_state": "approved"})
        lines.so_line._lab_refresh_delivered()
        return True
