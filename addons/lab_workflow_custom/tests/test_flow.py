from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLabFlow(TransactionCase):
    """Flusso end-to-end: Ordine > Progetto+task > Turno 80/20 > Foglio ore > Alert > Fattura."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True,
                                       mail_notrack=True))
        cls.partner = cls.env["res.partner"].create({"name": "Cliente Test Srl"})
        cls.pack = cls.env.ref("lab_workflow_custom.product_hours_pack_50").product_variant_id
        cls.fixed = cls.env.ref("lab_workflow_custom.product_dev_fixed").product_variant_id
        cls.ams = cls.env.ref("lab_workflow_custom.product_ams_monthly").product_variant_id
        cls.sales = new_test_user(cls.env, "t_sales", groups="lab_workflow_custom.group_lab_commerciale")
        cls.pm = new_test_user(cls.env, "t_pm", groups="lab_workflow_custom.group_lab_pm")
        cls.dev = new_test_user(cls.env, "t_dev", groups="lab_workflow_custom.group_lab_team")
        cls.admin_user = new_test_user(cls.env, "t_admin", groups="lab_workflow_custom.group_lab_amministrazione")
        cls.dev_employee = cls.env["hr.employee"].create(
            {"name": "Dev Test", "user_id": cls.dev.id, "hourly_cost": 35})
        cls.monday = date.today() - timedelta(days=date.today().weekday())

    def _confirmed_order(self, product, qty=1):
        order = self.env["sale.order"].with_user(self.sales).create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": qty})],
        })
        order.with_user(self.sales).action_confirm()
        return order.with_env(self.env)  # da qui in poi leggiamo come amministratore

    def _timesheet(self, task, hours):
        return self.env["account.analytic.line"].create({
            "name": "lavoro", "project_id": task.project_id.id, "task_id": task.id,
            "employee_id": self.dev_employee.id, "unit_amount": hours,
        })

    def test_01_products_configured(self):
        self.assertEqual(self.pack.service_policy, "ordered_prepaid")
        self.assertEqual(self.pack.service_tracking, "task_in_project")
        self.assertEqual(self.fixed.service_tracking, "task_in_project")
        self.assertTrue(self.ams.subscribable)
        self.assertEqual(self.ams.lab_monthly_hours, 20)

    def test_02_order_creates_project_and_default_tasks(self):
        order = self._confirmed_order(self.pack)
        line = order.order_line
        self.assertEqual(line.lab_sold_hours, 50)
        project = line.task_id.project_id
        self.assertTrue(project, "Il progetto deve essere creato alla conferma")
        self.assertEqual(project.privacy_visibility, "followers")
        names = project.task_ids.mapped("name")
        for expected in ("Analisi e Specifiche", "Project Management & Coordinamento", "Test & UAT"):
            self.assertIn(expected, names)
        self.assertEqual(len(project.task_ids), 4)
        self.assertAlmostEqual(sum(project.task_ids.mapped("allocated_hours")), 50)
        self.assertAlmostEqual(line.task_id.allocated_hours, 30)  # 60% sviluppo
        self.assertEqual(project.lab_sold_hours, 50)
        self.assertEqual(project.lab_estimated_hours, 50)

    def test_03_fixed_price_hours_per_unit(self):
        order = self._confirmed_order(self.fixed)
        project = order.order_line.task_id.project_id
        self.assertEqual(project.lab_sold_hours, 120)
        self.assertEqual(project.allocated_hours, 120)

    def test_04_planning_8020_and_confirm_creates_timesheet(self):
        order = self._confirmed_order(self.pack)
        task = order.order_line.task_id
        Slot = self.env["lab.planning.slot"].with_user(self.pm)
        slots = Slot.create([{
            "employee_id": self.dev_employee.id, "project_id": task.project_id.id,
            "task_id": task.id, "date": self.monday + timedelta(days=d),
            "allocated_hours": 6.4} for d in range(5)])  # 5 x 6.4 = 32h = 80%
        with self.assertRaises(ValidationError):
            Slot.create({"employee_id": self.dev_employee.id, "project_id": task.project_id.id,
                         "date": self.monday, "allocated_hours": 1})
        # il dipendente non vede le bozze
        self.assertFalse(self.env["lab.planning.slot"].with_user(self.dev).search([]))
        slots.action_publish()
        my = self.env["lab.planning.slot"].with_user(self.dev).search([])
        self.assertEqual(len(my), 5)
        with self.assertRaises(AccessError):
            my[0].write({"allocated_hours": 2})
        my[0].write({"confirmed_hours": 7})
        my[0].action_confirm()
        self.assertEqual(my[0].state, "confirmed")
        self.assertEqual(my[0].timesheet_id.unit_amount, 7)
        self.assertEqual(task.effective_hours, 7)

    def test_05_alert_75_90(self):
        order = self._confirmed_order(self.pack)
        task = order.order_line.task_id
        project = task.project_id
        project.user_id = self.pm
        self._timesheet(task, 30)  # 60% del progetto, 100% del task sviluppo (30h)
        self.assertEqual(task.lab_alert_level, "danger")
        self.assertEqual(project.lab_alert_level, "ok")
        self._timesheet(task, 8)   # 38/50 = 76%
        project.invalidate_recordset()
        self.assertEqual(project.lab_alert_level, "warning")
        self.assertEqual(project.lab_alert_notified, "warning")
        self.assertTrue(order.activity_ids.filtered(lambda a: a.user_id == self.sales))
        self.assertTrue(project.activity_ids.filtered(lambda a: a.user_id == self.pm))
        self._timesheet(task, 7)   # 45/50 = 90%
        project.invalidate_recordset()
        self.assertEqual(project.lab_alert_level, "danger")
        self.assertEqual(project.lab_alert_notified, "danger")

    def test_06_invoice_draft_by_sales_post_by_admin(self):
        order = self._confirmed_order(self.pack)
        invoice = order.with_user(self.sales)._create_invoices()
        self.assertEqual(invoice.state, "draft")
        with self.assertRaises(UserError):
            invoice.with_user(self.sales).action_post()
        invoice.with_user(self.admin_user).action_post()
        self.assertEqual(invoice.state, "posted")
        self.env.flush_all()
        margin = self.env["lab.margin.report"].search(
            [("project_id", "=", order.order_line.task_id.project_id.id)])
        self.assertEqual(margin.sold_amount, 2750)
        self.assertEqual(margin.invoiced_amount, 2750)

    def test_07_ams_monthly_alert_and_subscription(self):
        order = self._confirmed_order(self.ams)
        project = order.order_line.project_id
        self.assertTrue(project.lab_is_monthly)
        self.assertEqual(project.lab_sold_hours, 20)
        self.assertTrue(order.subscriptions_count)
        self.env["account.analytic.line"].create({
            "name": "ticket", "project_id": project.id, "employee_id": self.dev_employee.id,
            "unit_amount": 16})
        project.invalidate_recordset()
        self.assertEqual(project.lab_alert_level, "warning")
