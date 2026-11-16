from markupsafe import Markup

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
        self._lab_check_consultant_hours()
        return res

    def _lab_check_consultant_hours(self):
        """Fattura del consulente: le ore fatturate devono quadrare con quelle registrate in
        Odoo. Se non quadrano resta una nota ben visibile sulla fattura."""
        for move in self.filtered(lambda m: m.move_type in ("in_invoice", "in_refund")):
            rows = []
            for line in move.invoice_line_ids.filtered("lab_consultant_id"):
                if abs(line.lab_hours_difference) > 0.01:
                    rows.append(Markup("<li>%s: in fattura %s ore, registrate %s ore "
                                       "(differenza %+.2f)</li>") % (
                        line.lab_consultant_id.name, round(line.lab_billed_hours, 2),
                        round(line.lab_consultant_hours, 2), line.lab_hours_difference))
            if rows:
                move.message_post(body=Markup("⚠️ <b>Ore del consulente non quadrano</b>"
                                              "<ul>%s</ul>Controlla i fogli ore o chiedi una "
                                              "nota di credito.") % Markup("").join(rows),
                                  subtype_xmlid="mail.mt_note")

    def button_draft(self):
        # fattura riportata in bozza: le ore del consulente tornano "da fatturare"
        self.invoice_line_ids.lab_timesheet_ids.sudo().with_context(
            lab_skip_parallel=True).write({"lab_vendor_bill_line_id": False})
        return super().button_draft()
