from odoo import fields, models, tools


class LabMarginReport(models.Model):
    """Vista SQL di sola lettura: ricavi e costi per commessa.

    Ricavi = venduto (a corpo/canone: importo ordinato; T&M: ore consegnate x prezzo)
             + ribaltato al cliente (pass-through: consulenti e spese vive)
    Costi  = lavoro interno (fogli ore, gia' diviso nei giorni in parallelo)
             + AI (licenze ripartite) + consulenti esterni (fatture con il consulente
             indicato, oppure ore x tariffa finche' la fattura non c'e')
             + altri costi fornitori (fatture fornitori sulla commessa senza consulente)
    """
    _name = "lab.margin.report"
    _description = "Analisi margini per commessa"
    _auto = False
    _rec_name = "project_id"

    project_id = fields.Many2one("project.project", "Progetto", readonly=True)
    partner_id = fields.Many2one("res.partner", "Cliente", readonly=True)
    user_id = fields.Many2one("res.users", "Project Manager", readonly=True)
    company_id = fields.Many2one("res.company", "Azienda", readonly=True)
    sold_amount = fields.Float("Venduto (imponibile)", readonly=True)
    passthrough_revenue = fields.Float("Ribaltato al cliente", readonly=True)
    invoiced_amount = fields.Float("Fatturato (imponibile)", readonly=True)
    timesheet_cost = fields.Float("Costo lavoro interno", readonly=True)
    ai_cost = fields.Float("Costo AI", readonly=True)
    external_cost = fields.Float("Costo consulenti esterni", readonly=True)
    external_accrued = fields.Float("di cui maturato (fattura non ancora arrivata)",
                                    readonly=True)
    other_vendor_cost = fields.Float("Altri costi fornitori", readonly=True)
    passthrough_cost = fields.Float("di cui ribaltato al cliente", readonly=True)
    total_cost = fields.Float("Costo totale", readonly=True)
    margin = fields.Float("Margine lordo", readonly=True)
    margin_pct = fields.Float("Margine %", readonly=True, aggregator="avg")
    margin_excl_passthrough = fields.Float("Margine senza pass-through", readonly=True)
    hours_consumed = fields.Float("Ore consuntivate", readonly=True)
    hours_estimated = fields.Float("Ore stimate", readonly=True)
    hours_saved = fields.Float("Ore risparmiate (stimate - consuntivate)", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH base AS (
                    SELECT
                        p.id AS project_id,
                        p.partner_id, p.user_id, p.company_id,
                        COALESCE(s.sold, 0) AS sold,
                        COALESCE(s.invoiced, 0) + COALESCE(x.invoiced, 0) AS invoiced,
                        COALESCE(x.revenue, 0) AS passthrough_revenue,
                        COALESCE(t.cost, 0) AS labor,
                        COALESCE(t.hours, 0) AS hours,
                        COALESCE(t.accrued, 0) AS accrued,
                        COALESCE(a.cost, 0) AS ai,
                        COALESCE(b.consultant, 0) AS consultant_bills,
                        COALESCE(b.other, 0) AS other_bills,
                        COALESCE(b.reinvoiced, 0) + COALESCE(a.rebilled, 0) AS reinvoiced,
                        COALESCE(e.estimated, 0) AS estimated
                    FROM project_project p
                    LEFT JOIN (
                        SELECT COALESCE(sol.project_id, pt.project_id) AS project_id,
                               SUM(CASE WHEN tmpl.invoice_policy = 'delivery'
                                        THEN sol.price_unit * (1 - COALESCE(sol.discount, 0) / 100)
                                             * sol.qty_delivered
                                        ELSE sol.price_subtotal END) AS sold,
                               SUM(sol.untaxed_amount_invoiced) AS invoiced
                        FROM sale_order_line sol
                        JOIN sale_order so ON so.id = sol.order_id
                        LEFT JOIN project_task pt ON pt.id = sol.task_id
                        LEFT JOIN product_product pp ON pp.id = sol.product_id
                        LEFT JOIN product_template tmpl ON tmpl.id = pp.product_tmpl_id
                        WHERE so.state = 'sale' AND NOT COALESCE(sol.is_expense, FALSE)
                          AND COALESCE(sol.project_id, pt.project_id) IS NOT NULL
                        GROUP BY 1
                    ) s ON s.project_id = p.id
                    LEFT JOIN (
                        SELECT so.project_id,
                               SUM(sol.price_unit * (1 - COALESCE(sol.discount, 0) / 100)
                                   * sol.qty_delivered) AS revenue,
                               SUM(sol.untaxed_amount_invoiced) AS invoiced
                        FROM sale_order_line sol
                        JOIN sale_order so ON so.id = sol.order_id
                        WHERE so.state = 'sale' AND sol.is_expense AND so.project_id IS NOT NULL
                        GROUP BY so.project_id
                    ) x ON x.project_id = p.id
                    LEFT JOIN (
                        SELECT aal.project_id,
                               -SUM(aal.amount) AS cost,
                               SUM(aal.unit_amount) AS hours,
                               SUM(CASE WHEN aal.lab_vendor_bill_line_id IS NULL
                                        THEN COALESCE(aal.lab_accrued_external_cost, 0)
                                        ELSE 0 END) AS accrued
                        FROM account_analytic_line aal
                        WHERE aal.project_id IS NOT NULL
                        GROUP BY aal.project_id
                    ) t ON t.project_id = p.id
                    LEFT JOIN (
                        SELECT project_id, SUM(amount) AS cost,
                               SUM(CASE WHEN sale_line_id IS NOT NULL THEN amount ELSE 0 END)
                                   AS rebilled
                        FROM lab_cost_allocation
                        WHERE project_id IS NOT NULL
                        GROUP BY project_id
                    ) a ON a.project_id = p.id
                    LEFT JOIN (
                        SELECT aal.account_id,
                               -SUM(CASE WHEN aml.lab_consultant_id IS NOT NULL
                                         THEN aal.amount ELSE 0 END) AS consultant,
                               -SUM(CASE WHEN aml.lab_consultant_id IS NULL
                                         THEN aal.amount ELSE 0 END) AS other,
                               -SUM(CASE WHEN aal.so_line IS NOT NULL THEN aal.amount ELSE 0 END)
                                   AS reinvoiced
                        FROM account_analytic_line aal
                        LEFT JOIN account_move_line aml ON aml.id = aal.move_line_id
                        WHERE aal.category = 'vendor_bill' AND aal.project_id IS NULL
                        GROUP BY aal.account_id
                    ) b ON b.account_id = p.account_id
                    LEFT JOIN (
                        SELECT project_id, SUM(allocated_hours) AS estimated
                        FROM project_task
                        WHERE active AND parent_id IS NULL
                        GROUP BY project_id
                    ) e ON e.project_id = p.id
                    WHERE p.active
                )
                SELECT
                    project_id AS id,
                    project_id, partner_id, user_id, company_id,
                    sold AS sold_amount,
                    passthrough_revenue,
                    invoiced AS invoiced_amount,
                    labor AS timesheet_cost,
                    ai AS ai_cost,
                    consultant_bills + accrued AS external_cost,
                    other_bills AS other_vendor_cost,
                    accrued AS external_accrued,
                    reinvoiced AS passthrough_cost,
                    labor + ai + consultant_bills + other_bills + accrued AS total_cost,
                    sold + passthrough_revenue - (labor + ai + consultant_bills + other_bills + accrued) AS margin,
                    CASE WHEN sold + passthrough_revenue > 0
                         THEN (sold + passthrough_revenue - (labor + ai + consultant_bills + other_bills + accrued))
                              / (sold + passthrough_revenue) * 100
                         ELSE 0 END AS margin_pct,
                    sold - (labor + ai + consultant_bills + other_bills + accrued - reinvoiced) AS margin_excl_passthrough,
                    hours AS hours_consumed,
                    estimated AS hours_estimated,
                    estimated - hours AS hours_saved
                FROM base
            )
        """)
