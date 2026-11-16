"""Panoramica del PM sul progetto: un solo margine, pulsanti, cronologia nel chatter, nomi brevi."""
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLabPmOverview(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Cliente Panoramica Srl",
                                                     "is_company": True})
        cls.pack = cls.env.ref("lab_workflow_custom.product_hours_pack_50").product_variant_id
        cls.sales = new_test_user(cls.env, "t_ov_sales",
                                  groups="lab_workflow_custom.group_lab_commerciale")
        cls.dev = new_test_user(cls.env, "t_ov_dev", groups="lab_workflow_custom.group_lab_team")
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Dev Panoramica", "user_id": cls.dev.id, "hourly_cost": 40})

    def _order(self, ref=False):
        order = self.env["sale.order"].with_user(self.sales).create({
            "partner_id": self.partner.id, "client_order_ref": ref,
            "order_line": [(0, 0, {"product_id": self.pack.id, "product_uom_qty": 1})],
        })
        order.with_user(self.sales).action_confirm()
        order = order.with_env(self.env)
        return order, order.order_line.task_id.project_id

    def _notes(self, project):
        return " | ".join(project.message_ids.mapped("body"))

    def test_01_short_names(self):
        _order, project = self._order(ref="Portale B2B")
        self.assertEqual(project.name, "Portale B2B")
        order2, project2 = self._order()
        self.assertEqual(project2.name, "Cliente Panoramica Srl – %s" % self.pack.name)
        self.assertNotIn(order2.name, project2.name)
        self.assertEqual(project2.sale_order_id, order2, "l'ordine resta collegato")
        # vecchio nome lungo: viene accorciato; un nome scelto a mano resta
        project2.name = "%s - %s - [X] Prodotto" % ("Rif", order2.name)
        project.name = "Nome scelto dal PM"
        self.env["project.project"]._lab_short_names()
        self.assertEqual(project2.name, "Cliente Panoramica Srl – %s" % self.pack.name)
        self.assertEqual(project.name, "Nome scelto dal PM")

    def test_02_one_margin_in_odoo_dashboard(self):
        _order, project = self._order()
        task = project.task_ids[:1]
        self.env["account.analytic.line"].create({
            "name": "lavoro", "project_id": project.id, "task_id": task.id,
            "employee_id": self.employee.id, "unit_amount": 5})
        project.invalidate_recordset()
        items = project._get_profitability_items()
        revenues = items["revenues"]["total"]
        costs = items["costs"]["total"]
        self.assertAlmostEqual(revenues["invoiced"] + revenues["to_invoice"], project.lab_revenue)
        self.assertAlmostEqual(-(costs["billed"] + costs["to_bill"]), project.lab_total_cost)
        self.assertAlmostEqual(project.lab_total_cost, 200.0)
        labels = project._get_profitability_labels()
        for item in items["revenues"]["data"] + items["costs"]["data"]:
            self.assertIn(item["id"], labels)
        panel = project.get_panel_data()
        self.assertEqual(panel["profitability_items"]["costs"]["total"], costs)

    def test_03_overview_buttons(self):
        _order, project = self._order()
        task = project.task_ids[:1]
        self.env["account.analytic.line"].create({
            "name": "lavoro", "project_id": project.id, "task_id": task.id,
            "employee_id": self.employee.id, "unit_amount": 2})
        project.invalidate_recordset()
        self.assertEqual(project.lab_timesheet_count, 1)
        self.assertEqual(project.lab_to_invoice, project.lab_revenue - project.lab_invoiced_amount)
        self.assertIn(("project_id", "=", project.id), project.action_lab_timesheets()["domain"])
        self.assertIn(("project_id", "=", project.id), project.action_lab_margin()["domain"])
        self.assertEqual(project.lab_invoice_count, 0)
        self.assertEqual(project.action_lab_invoices()["res_model"], "account.move")

    def test_04_history_in_chatter(self):
        order, project = self._order()
        self.assertIn("Ordine di vendita confermato", self._notes(project))
        self.assertIn(order.name, self._notes(project))
        # ticket di assistenza aperto e chiuso
        ticket = self.env["helpdesk.ticket"].create({
            "name": "Errore in stampa", "description": "<p>x</p>",
            "partner_id": self.partner.id, "project_id": project.id})
        self.assertIn("Ticket aperto", self._notes(project))
        ticket.stage_id = self.env.ref("helpdesk_mgmt.helpdesk_ticket_stage_done")
        self.assertIn("Ticket chiuso", self._notes(project))
        # SAL (aggiornamento di stato della Dashboard)
        self.env["project.update"].create({
            "name": "SAL di novembre", "project_id": project.id, "status": "at_risk",
            "progress": 40, "description": "<p>Consegna slittata di una settimana</p>"})
        notes = self._notes(project)
        self.assertIn("SAL di novembre", notes)
        self.assertIn("40%", notes)
        self.assertIn("Consegna slittata", notes)
        # incontro dal Calendario collegato al progetto
        self.env["calendar.event"].create({
            "name": "Call di allineamento", "start": "2026-11-20 09:00:00",
            "stop": "2026-11-20 10:00:00",
            "res_model_id": self.env["ir.model"]._get_id("project.project"),
            "res_id": project.id, "partner_ids": [(6, 0, self.partner.ids)]})
        notes = self._notes(project)
        self.assertIn("Incontro pianificato", notes)
        self.assertIn("Call di allineamento", notes)
        # attività SAL disponibile sul progetto
        sal = self.env.ref("lab_workflow_custom.mail_activity_type_sal")
        self.assertEqual(sal.res_model, "project.project")

    def test_05_invoice_in_chatter_and_button(self):
        order, project = self._order()
        order.order_line.qty_delivered = 1
        invoice = order._create_invoices()
        invoice.action_post()
        self.assertIn("Fattura cliente emessa", self._notes(project))
        project.invalidate_recordset()
        self.assertEqual(project.lab_invoice_count, 1)

    def test_06_economics_hidden_from_team(self):
        """Sviluppatori e Supporto non leggono ricavi, costi e margini, nemmeno via API."""
        from odoo.exceptions import AccessError
        _order, project = self._order()
        project.message_subscribe(partner_ids=self.dev.partner_id.ids)  # lo vede
        as_dev = project.with_user(self.dev)
        self.assertTrue(as_dev.name)
        for field in ("lab_margin", "lab_revenue", "lab_total_cost", "lab_cost_labor"):
            with self.assertRaises(AccessError):
                as_dev.read([field])
        self.assertFalse(as_dev._show_profitability(), "niente pannello Redditività")
        pm = new_test_user(self.env, "t_ov_pm", groups="lab_workflow_custom.group_lab_pm")
        self.assertIsInstance(project.with_user(pm).read(["lab_margin"])[0]["lab_margin"], float)
