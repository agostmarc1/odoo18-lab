from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # ---- Fatture dei consulenti esterni -------------------------------------
    lab_consultant_id = fields.Many2one(
        "hr.employee", "Consulente", domain="[('lab_resource_type', '=', 'external')]",
        help="Consulente esterno a cui si riferisce questa riga della fattura fornitore. "
             "Alla conferma Odoo collega le sue ore non ancora fatturate su questa commessa.")
    lab_timesheet_ids = fields.One2many(
        "account.analytic.line", "lab_vendor_bill_line_id", "Ore del consulente")
    lab_accrued_amount = fields.Monetary(
        "Costo maturato ore", compute="_compute_lab_consultant_variance",
        currency_field="company_currency_id")
    lab_variance = fields.Monetary(
        "Scostamento fattura - ore", compute="_compute_lab_consultant_variance",
        currency_field="company_currency_id",
        help="Importo fatturato dal consulente meno il costo maturato delle ore collegate. "
             "Positivo: ha fatturato più delle ore segnate.")

    lab_consultant_hours = fields.Float(
        "Ore registrate dal consulente", compute="_compute_lab_consultant_hours",
        help="Ore dei fogli ore del consulente collegate a questa riga.")
    lab_billed_hours = fields.Float(
        "Ore in fattura", compute="_compute_lab_consultant_hours",
        help="Quantità della riga convertita in ore (se la tariffa è a giornata: giorni × ore "
             "della sua giornata).")
    lab_hours_difference = fields.Float(
        "Differenza ore (fattura - registrate)", compute="_compute_lab_consultant_hours")

    @api.depends("lab_timesheet_ids.unit_amount", "quantity", "lab_consultant_id")
    def _compute_lab_consultant_hours(self):
        for line in self:
            consultant = line.lab_consultant_id.sudo()
            logged = sum(line.sudo().lab_timesheet_ids.mapped("unit_amount"))
            billed = line.quantity if consultant else 0.0
            if consultant and consultant.lab_external_rate_unit == "day":
                billed *= self.env["account.analytic.line"]._lab_day_hours(consultant)
            line.lab_consultant_hours = logged
            line.lab_billed_hours = billed
            line.lab_hours_difference = (billed - logged) if consultant else 0.0

    @api.depends("lab_timesheet_ids.lab_accrued_external_cost", "balance")
    def _compute_lab_consultant_variance(self):
        for line in self:
            accrued = sum(line.lab_timesheet_ids.mapped("lab_accrued_external_cost"))
            line.lab_accrued_amount = accrued
            line.lab_variance = (line.balance - accrued) if line.lab_consultant_id else 0.0

    def _lab_projects(self):
        """Progetti indicati nella distribuzione analitica della riga."""
        account_ids = set()
        for key in self.analytic_distribution or {}:
            account_ids.update(int(a) for a in str(key).split(","))
        if not account_ids:
            return self.env["project.project"]
        return self.env["project.project"].sudo().search([("account_id", "in", list(account_ids))])

    def _lab_link_consultant_timesheets(self):
        for line in self.filtered("lab_consultant_id"):
            projects = line._lab_projects()
            if not projects:
                continue
            date_limit = line.move_id.invoice_date or line.move_id.date
            timesheets = self.env["account.analytic.line"].sudo().search([
                ("employee_id", "=", line.lab_consultant_id.id),
                ("project_id", "in", projects.ids),
                ("lab_vendor_bill_line_id", "=", False),
                ("date", "<=", date_limit),
            ])
            timesheets.with_context(lab_skip_parallel=True).write(
                {"lab_vendor_bill_line_id": line.id})

    # ---- Ribaltamento al cliente (pass-through) --------------------------------
    def _sale_determine_order(self):
        """Si ribalta solo sui contratti a consuntivo (T&M). Sui contratti a corpo
        e sui canoni il costo resta un costo e riduce il margine."""
        # La ricerca standard dell'ordine passa dal progetto, che è riservato agli invitati:
        # chi registra la fattura (es. l'Amministrazione) spesso non lo vede, e senza sudo il
        # ribaltamento salterebbe in silenzio. La riga sull'ordine resta creata con i permessi
        # dell'utente.
        mapping = super(AccountMoveLine, self.sudo())._sale_determine_order()
        return {
            line_id: order.with_env(self.env) for line_id, order in mapping.items()
            if order and order.sudo().project_id._lab_contract_type() == "tm"
        }

    def _sale_get_invoice_price(self, order):
        price = super()._sale_get_invoice_price(order)
        if self.product_id.expense_policy == "cost":
            markup = order.sudo().project_id.lab_passthrough_markup_pct or 0.0
            price = order.currency_id.round(price * (1 + markup / 100.0))
        return price
