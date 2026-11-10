from datetime import date

from odoo import api, fields, models

WEEKS_PER_MONTH = 52.0 / 12.0
# costi e tariffe: visibili solo a HR, Amministrazione e Project Manager
COST_GROUPS = ("hr.group_hr_user,lab_workflow_custom.group_lab_amministrazione,"
               "lab_workflow_custom.group_lab_pm")


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    lab_resource_type = fields.Selection(
        [("internal", "Dipendente interno"), ("external", "Consulente esterno")],
        "Tipo risorsa", default="internal", required=True, groups=COST_GROUPS,
        help="Interno: costo = costo orario (+ quota AI). Esterno: costo dalla sua fattura, "
             "nel frattempo ore × tariffa concordata.")
    lab_vendor_id = fields.Many2one(
        "res.partner", "Fornitore che fattura", groups=COST_GROUPS,
        help="Il libero professionista o l'agenzia che manda la fattura all'azienda.")
    lab_external_rate = fields.Monetary(
        "Tariffa concordata", currency_field="currency_id", groups=COST_GROUPS)
    lab_external_rate_unit = fields.Selection(
        [("hour", "all'ora"), ("day", "a giornata")], "Unità tariffa", default="day",
        groups=COST_GROUPS)
    lab_parallel_factor = fields.Float(
        "Fattore parallelo", default=1.0, groups=COST_GROUPS,
        help="Quante ore-progetto può gestire per ogni ora reale lavorando in parallelo con "
             "l'AI (es. senior con Claude Code 1,5; junior 1,0). Moltiplica il limite "
             "settimanale della regola 80/20 in Pianificazione.")
    lab_ai_license_ids = fields.One2many(
        "lab.ai.license", "employee_id", "Licenze AI", groups=COST_GROUPS)
    lab_ai_monthly_cost = fields.Monetary(
        "Licenze AI al mese", compute="_compute_lab_ai_cost", currency_field="currency_id",
        groups=COST_GROUPS)
    lab_ai_hourly_uplift = fields.Float(
        "Maggiorazione AI all'ora (€)", compute="_compute_lab_ai_cost", digits=(16, 4),
        groups=COST_GROUPS,
        help="Licenze AI mensili / ore produttive standard del mese "
             "(limite settimanale 80/20 × 52 / 12).")
    lab_fully_loaded_cost = fields.Monetary(
        "Costo pieno all'ora", compute="_compute_lab_ai_cost", currency_field="currency_id",
        groups=COST_GROUPS,
        help="Costo orario + maggiorazione AI. Utile per preventivi e stime.")

    @api.model
    def _lab_standard_month_hours(self):
        weekly = self.env["lab.planning.slot"]._max_weekly_hours()
        return weekly * WEEKS_PER_MONTH

    @api.depends("lab_ai_license_ids.monthly_cost", "lab_ai_license_ids.date_start",
                 "lab_ai_license_ids.date_end", "hourly_cost", "lab_resource_type")
    def _compute_lab_ai_cost(self):
        today = date.today()
        std_hours = self._lab_standard_month_hours()
        for employee in self:
            licenses = employee.lab_ai_license_ids.filtered(lambda l: l._is_active_on(today))
            monthly = sum(licenses.mapped("monthly_cost"))
            uplift = monthly / std_hours if std_hours else 0.0
            base = (employee._lab_external_hourly_rate()
                    if employee.lab_resource_type == "external" else employee.hourly_cost)
            employee.lab_ai_monthly_cost = monthly
            employee.lab_ai_hourly_uplift = uplift
            employee.lab_fully_loaded_cost = base + uplift

    def _lab_external_hourly_rate(self):
        self.ensure_one()
        employee = self.sudo()
        if employee.lab_resource_type != "external":
            return 0.0
        if employee.lab_external_rate_unit == "day":
            day_hours = self.env["account.analytic.line"]._lab_day_hours(employee)
            return employee.lab_external_rate / day_hours if day_hours else 0.0
        return employee.lab_external_rate

    @api.onchange("lab_resource_type")
    def _onchange_lab_resource_type(self):
        if self.lab_resource_type == "external":
            self.hourly_cost = 0.0
