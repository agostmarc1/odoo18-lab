from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    lab_sold_hours = fields.Float(
        "Ore vendute", compute="_compute_lab_sold_hours", store=True,
        help="Ore vendute su questa riga, convertite in ore.",
    )

    @api.depends("product_id", "product_uom_qty", "product_uom")
    def _compute_lab_sold_hours(self):
        uom_hour = self.env.ref("uom.product_uom_hour")
        for line in self:
            product = line.product_id
            if not product or product.type != "service":
                line.lab_sold_hours = 0.0
            elif product.lab_monthly_hours:
                line.lab_sold_hours = product.lab_monthly_hours * line.product_uom_qty
            elif product.lab_hours_per_unit:
                line.lab_sold_hours = product.lab_hours_per_unit * line.product_uom_qty
            elif line.product_uom and line.product_uom.category_id == uom_hour.category_id:
                line.lab_sold_hours = line.product_uom._compute_quantity(
                    line.product_uom_qty, uom_hour, raise_if_failure=False)
            else:
                # stessa logica di Odoo: venduto a unità = ore
                line.lab_sold_hours = line.product_uom_qty

    def _timesheet_create_project(self):
        project = super()._timesheet_create_project()
        # Ore allocate del progetto = ore vendute (con 'Ore per unità')
        lines = self.order_id.order_line.filtered(
            lambda l: l.is_service
            and l.product_id.service_tracking in ("task_in_project", "project_only")
            and l.product_id.project_template_id == self.product_id.project_template_id)
        project.write({
            "allocated_hours": sum(lines.mapped("lab_sold_hours")),
            # solo gli utenti invitati e gli assegnatari dei task vedono la commessa
            "privacy_visibility": "followers",
        })
        salesman = self.order_id.user_id.partner_id
        if salesman:
            project.message_subscribe(partner_ids=salesman.ids)
        return project

    def _timesheet_create_task_prepare_values(self, project):
        vals = super()._timesheet_create_task_prepare_values(project)
        if self.product_id.lab_hours_per_unit or self.product_id.lab_monthly_hours:
            vals["allocated_hours"] = self.lab_sold_hours
        return vals

    def _timesheet_service_generation(self):
        res = super()._timesheet_service_generation()
        for line in self.filtered(
                lambda l: l.product_id.lab_create_default_tasks and l.task_id):
            project = line.sudo().task_id.project_id
            if not project.lab_default_tasks_done:
                self.env["lab.default.task"].sudo()._create_default_tasks(line)
        return res
