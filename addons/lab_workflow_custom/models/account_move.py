from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        user = self.env.user
        if (user.has_group("lab_workflow_custom.group_lab_commerciale")
                and not user.has_group("lab_workflow_custom.group_lab_amministrazione")
                and not self.env.su):
            raise UserError(_(
                "Il Commerciale può preparare le fatture in bozza, ma la conferma "
                "(registrazione) spetta all'Amministrazione."))
        res = super().action_post()
        # fatture dei consulenti: collega le loro ore non ancora fatturate
        self.filtered(lambda m: m.move_type in ("in_invoice", "in_refund")
                      ).invoice_line_ids._lab_link_consultant_timesheets()
        return res

    def button_draft(self):
        # fattura riportata in bozza: le ore del consulente tornano "da fatturare"
        self.invoice_line_ids.lab_timesheet_ids.sudo().with_context(
            lab_skip_parallel=True).write({"lab_vendor_bill_line_id": False})
        return super().button_draft()
