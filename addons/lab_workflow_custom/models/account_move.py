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
        return super().action_post()
