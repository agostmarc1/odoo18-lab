from odoo import api, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.project_id._lab_check_hours_alert()
        return lines

    def write(self, vals):
        projects = self.project_id
        res = super().write(vals)
        (projects | self.project_id)._lab_check_hours_alert()
        return res

    def unlink(self):
        projects = self.project_id
        res = super().unlink()
        projects.exists()._lab_check_hours_alert()
        return res
