"""Soluzioni di settore: la stessa offerta venduta a più clienti dello stesso settore.

Una soluzione raccoglie i prodotti a listino (setup standard con il suo modello di progetto,
canone), le installazioni (commesse nate da quei prodotti o collegate a mano, es. il cliente
pilota) e le trattative. Il cruscotto mostra se il business scala: ore per installazione che
scendono rispetto alla prima, margine medio, valore delle trattative aperte.
I numeri economici arrivano da lab.margin.report: un solo calcolo dei margini.
"""
from odoo import api, fields, models

from .project_project import ECONOMICS_GROUPS


class LabVertical(models.Model):
    _name = "lab.vertical"
    _description = "Soluzione di settore"
    _inherit = ["mail.thread"]
    _order = "sequence, name"

    name = fields.Char("Soluzione", required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    user_id = fields.Many2one("res.users", "Responsabile", tracking=True,
                              default=lambda self: self.env.user)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    description = fields.Html("Cosa comprende")
    product_tmpl_ids = fields.One2many("product.template", "lab_vertical_id", "Offerta a listino")
    project_ids = fields.One2many("project.project", "lab_vertical_id", "Installazioni")
    lead_ids = fields.One2many("crm.lead", "lab_vertical_id", "Opportunità")

    standard_hours = fields.Float(
        "Ore standard per installazione", compute="_compute_lab_stats",
        help="Ore del setup standard a listino (prodotto con 'Ore per unità').")
    install_count = fields.Integer("Installazioni", compute="_compute_lab_stats")
    customer_count = fields.Integer("Clienti", compute="_compute_lab_stats")
    pipeline_count = fields.Integer("Trattative aperte", compute="_compute_lab_stats")
    pipeline_amount = fields.Monetary("Valore trattative", compute="_compute_lab_stats",
                                      help="Ricavo atteso delle opportunità non ancora vinte.")
    pilot_hours = fields.Float("Ore della prima installazione", compute="_compute_lab_stats")
    hours_saved = fields.Float(
        "Ore risparmiate per installazione", compute="_compute_lab_stats",
        help="Ore vendute della prima installazione meno le ore del setup standard: "
             "quanto lavoro in meno costa ogni nuovo cliente grazie allo standard.")
    avg_sold_hours = fields.Float("Ore vendute medie", compute="_compute_lab_stats")
    avg_consumed_hours = fields.Float("Ore consuntivate medie", compute="_compute_lab_stats")
    revenue = fields.Monetary("Venduto", compute="_compute_lab_economics", groups=ECONOMICS_GROUPS)
    total_cost = fields.Monetary("Costi", compute="_compute_lab_economics", groups=ECONOMICS_GROUPS)
    margin = fields.Monetary("Margine", compute="_compute_lab_economics", groups=ECONOMICS_GROUPS)
    margin_pct = fields.Float("Margine %", compute="_compute_lab_economics", groups=ECONOMICS_GROUPS,
                              digits=(5, 1))

    def _lab_projects(self):
        self.ensure_one()
        return self.sudo().with_context(active_test=True).project_ids.sorted(
            lambda p: (p.create_date or fields.Datetime.now(), p.id))

    @api.depends("product_tmpl_ids.lab_hours_per_unit", "project_ids", "lead_ids.stage_id",
                 "lead_ids.expected_revenue", "lead_ids.active")
    def _compute_lab_stats(self):
        for vertical in self:
            setup = vertical.sudo().product_tmpl_ids.filtered(
                lambda t: t.lab_hours_per_unit and not t.lab_monthly_hours)
            projects = vertical._lab_projects() if vertical.id else self.env["project.project"]
            leads = vertical.sudo().lead_ids.filtered(
                lambda l: l.active and l.type == "opportunity" and not l.stage_id.is_won)
            sold = projects.mapped("lab_sold_hours")
            vertical.standard_hours = max(setup.mapped("lab_hours_per_unit"), default=0.0)
            vertical.install_count = len(projects)
            vertical.customer_count = len(projects.partner_id.commercial_partner_id)
            vertical.pipeline_count = len(leads)
            vertical.pipeline_amount = sum(leads.mapped("expected_revenue"))
            vertical.pilot_hours = sold[0] if sold else 0.0
            vertical.hours_saved = (max(vertical.pilot_hours - vertical.standard_hours, 0.0)
                                    if sold and vertical.standard_hours else 0.0)
            vertical.avg_sold_hours = sum(sold) / len(sold) if sold else 0.0
            vertical.avg_consumed_hours = (sum(projects.mapped("lab_consumed_hours")) / len(projects)
                                           if projects else 0.0)

    def _compute_lab_economics(self):
        Report = self.env["lab.margin.report"].sudo()
        for vertical in self:
            rows = Report.search([("project_id", "in", vertical._lab_projects().ids)]) if vertical.id \
                else Report
            revenue = sum(rows.mapped("sold_amount")) + sum(rows.mapped("passthrough_revenue"))
            cost = sum(rows.mapped("total_cost"))
            vertical.revenue = revenue
            vertical.total_cost = cost
            vertical.margin = revenue - cost
            vertical.margin_pct = (revenue - cost) / revenue * 100.0 if revenue else 0.0

    def _lab_action(self, model, name, records, views="list,form", extra_ctx=None):
        return {
            "type": "ir.actions.act_window", "name": "%s – %s" % (name, self.name),
            "res_model": model, "view_mode": views,
            "domain": [("id", "in", records.ids)],
            "context": dict({"default_lab_vertical_id": self.id}, **(extra_ctx or {})),
        }

    def action_lab_installations(self):
        self.ensure_one()
        return self._lab_action("project.project", "Installazioni", self._lab_projects(), "kanban,list,form")

    def action_lab_pipeline(self):
        self.ensure_one()
        leads = self.lead_ids.filtered(lambda l: not l.stage_id.is_won)
        return self._lab_action("crm.lead", "Trattative", leads, "kanban,list,form",
                                {"default_type": "opportunity"})

    def action_lab_products(self):
        self.ensure_one()
        return self._lab_action("product.template", "Offerta a listino", self.product_tmpl_ids)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    lab_vertical_id = fields.Many2one(
        "lab.vertical", "Soluzione di settore", index=True,
        help="Le commesse nate da questo prodotto contano come installazioni della soluzione.")


class CrmLead(models.Model):
    _inherit = "crm.lead"

    lab_vertical_id = fields.Many2one("lab.vertical", "Soluzione di settore", index=True, tracking=True)


class ProjectProject(models.Model):
    _inherit = "project.project"

    lab_vertical_id = fields.Many2one("lab.vertical", "Soluzione di settore", index=True, copy=False)
    lab_instance_url = fields.Char(
        "Ambiente del cliente", copy=False,
        help="Indirizzo dell'Odoo dedicato del cliente (es. l'istanza su Cloudpepper).")
