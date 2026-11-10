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

    # ---- Consumo del pacchetto: ogni ora scalata ha il suo task ----------------
    lab_consumed_hours = fields.Float(
        "Ore scalate", compute="_compute_lab_package",
        help="Ore dei fogli ore collegati a questa riga (anche quelle parallele da approvare).")
    lab_remaining_hours = fields.Float(
        "Ore residue", compute="_compute_lab_package",
        help="Ore vendute meno ore scalate. Negativo: pacchetto sforato.")
    lab_task_count = fields.Integer("N. task", compute="_compute_lab_package")

    def _compute_lab_package(self):
        groups = {}
        ids = [i for i in self.ids if isinstance(i, int)]
        if ids:
            for so_line, task, hours in self.env["account.analytic.line"].sudo()._read_group(
                    [("so_line", "in", ids), ("project_id", "!=", False)],
                    ["so_line", "task_id"], ["unit_amount:sum"]):
                total, tasks = groups.get(so_line.id, (0.0, 0))
                groups[so_line.id] = (total + hours, tasks + (1 if task else 0))
        for line in self:
            consumed, tasks = groups.get(line.id, (0.0, 0)) if isinstance(line.id, int) else (0.0, 0)
            line.lab_consumed_hours = consumed
            line.lab_remaining_hours = line.lab_sold_hours - consumed
            line.lab_task_count = tasks

    def action_lab_open_consumption(self):
        """Fogli ore scalati da questo pacchetto, raggruppati per task."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Ore scalate: %s" % self.display_name,
            "res_model": "account.analytic.line",
            "view_mode": "list,pivot,form",
            "views": [(self.env.ref("hr_timesheet.hr_timesheet_line_tree").id, "list"),
                      (False, "pivot"), (False, "form")],
            "domain": [("so_line", "=", self.id), ("project_id", "!=", False)],
            "context": {"group_by": ["task_id"], "create": False,
                        "default_so_line": self.id},
        }

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
        # Canone di assistenza (AMS): il Supporto segue la commessa e ne vede i task
        if any(l.product_id.lab_monthly_hours for l in lines):
            support = self.env.ref("lab_workflow_custom.group_lab_support").sudo().users
            if support:
                project.message_subscribe(partner_ids=support.partner_id.ids)
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

    # ---- Ore parallele: finché il PM non le approva non sono fatturabili --------
    def _timesheet_compute_delivered_quantity_domain(self):
        domain = super()._timesheet_compute_delivered_quantity_domain()
        return domain + [("lab_parallel_state", "!=", "to_approve")]

    def _lab_refresh_delivered(self):
        lines = self.sudo().filtered(lambda l: l.qty_delivered_method == "timesheet")
        if lines:
            lines._compute_qty_delivered()
