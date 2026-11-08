from odoo import fields, models, tools


class LabMarginReport(models.Model):
    """Vista SQL di sola lettura: ricavi venduti/fatturati vs costo fogli ore per progetto."""
    _name = "lab.margin.report"
    _description = "Analisi margini per commessa"
    _auto = False
    _rec_name = "project_id"

    project_id = fields.Many2one("project.project", "Progetto", readonly=True)
    partner_id = fields.Many2one("res.partner", "Cliente", readonly=True)
    user_id = fields.Many2one("res.users", "Project Manager", readonly=True)
    company_id = fields.Many2one("res.company", "Azienda", readonly=True)
    sold_amount = fields.Float("Venduto (imponibile)", readonly=True)
    invoiced_amount = fields.Float("Fatturato (imponibile)", readonly=True)
    timesheet_cost = fields.Float("Costo fogli ore", readonly=True)
    margin = fields.Float("Margine (venduto - costo)", readonly=True)
    hours_consumed = fields.Float("Ore consuntivate", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    p.id AS id,
                    p.id AS project_id,
                    p.partner_id AS partner_id,
                    p.user_id AS user_id,
                    p.company_id AS company_id,
                    COALESCE(s.sold, 0) AS sold_amount,
                    COALESCE(s.invoiced, 0) AS invoiced_amount,
                    COALESCE(-t.cost, 0) AS timesheet_cost,
                    COALESCE(s.sold, 0) + COALESCE(t.cost, 0) AS margin,
                    COALESCE(t.hours, 0) AS hours_consumed
                FROM project_project p
                LEFT JOIN (
                    SELECT COALESCE(sol.project_id, pt.project_id) AS project_id,
                           SUM(sol.price_subtotal) AS sold,
                           SUM(sol.untaxed_amount_invoiced) AS invoiced
                    FROM sale_order_line sol
                    JOIN sale_order so ON so.id = sol.order_id
                    LEFT JOIN project_task pt ON pt.id = sol.task_id
                    WHERE so.state = 'sale'
                      AND COALESCE(sol.project_id, pt.project_id) IS NOT NULL
                    GROUP BY 1
                ) s ON s.project_id = p.id
                LEFT JOIN (
                    SELECT aal.project_id, SUM(aal.amount) AS cost,
                           SUM(aal.unit_amount) AS hours
                    FROM account_analytic_line aal
                    WHERE aal.project_id IS NOT NULL
                    GROUP BY aal.project_id
                ) t ON t.project_id = p.id
                WHERE p.active
            )
        """)
