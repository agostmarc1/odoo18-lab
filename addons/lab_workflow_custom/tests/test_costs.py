from datetime import date, timedelta

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLabCosts(TransactionCase):
    """Costi commessa: lavoro in parallelo, licenze AI, consulenti esterni, pass-through."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True,
                                       mail_notrack=True))
        cls.partner = cls.env["res.partner"].create({"name": "Cliente Costi Srl"})
        cls.vendor = cls.env["res.partner"].create({"name": "Consulente Srl", "supplier_rank": 1})
        cls.pack = cls.env.ref("lab_workflow_custom.product_hours_pack_50").product_variant_id
        cls.tm = cls.env.ref("lab_workflow_custom.product_tm_hourly").product_variant_id
        cls.cons_product = cls.env.ref(
            "lab_workflow_custom.product_external_consultant").product_variant_id
        cls.pm = new_test_user(cls.env, "c_pm", groups="lab_workflow_custom.group_lab_pm")
        cls.dev_user = new_test_user(cls.env, "c_dev", groups="lab_workflow_custom.group_lab_team")
        # le fatture fornitori le conferma l'Amministrazione, che NON vede le commesse riservate
        cls.accountant = new_test_user(
            cls.env, "c_amm", groups="lab_workflow_custom.group_lab_amministrazione")
        cls.dev = cls.env["hr.employee"].create({
            "name": "Dev Costi", "user_id": cls.dev_user.id, "hourly_cost": 35})
        cls.pm_employee = cls.env["hr.employee"].create({
            "name": "PM Costi", "user_id": cls.pm.id, "hourly_cost": 45})
        cls.consultant = cls.env["hr.employee"].create({
            "name": "Consulente Esterno", "lab_resource_type": "external",
            "lab_vendor_id": cls.vendor.id, "lab_external_rate": 400,
            "lab_external_rate_unit": "day", "hourly_cost": 0})
        cls.day = date.today()

    # ---- helper ---------------------------------------------------------------
    def _order(self, product, qty=1):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": qty})],
        })
        order.action_confirm()
        return order

    def _ts(self, task, employee, hours, day=None):
        return self.env["account.analytic.line"].create({
            "name": "lavoro", "project_id": task.project_id.id, "task_id": task.id,
            "employee_id": employee.id, "unit_amount": hours, "date": day or self.day})

    def _bill(self, project, hours, price, consultant=None):
        bill = self.env["account.move"].create({
            "move_type": "in_invoice", "partner_id": self.vendor.id,
            "invoice_date": self.day,
            "invoice_line_ids": [(0, 0, {
                "product_id": self.cons_product.id, "quantity": hours, "price_unit": price,
                "analytic_distribution": {str(project.account_id.id): 100},
                "lab_consultant_id": consultant.id if consultant else False,
                "tax_ids": [(6, 0, [])],
            })],
        })
        self.assertFalse(project.with_user(self.accountant).search_count(
            [("id", "=", project.id)]), "Commessa riservata: l'Amministrazione non la vede")
        bill.with_user(self.accountant).action_post()
        return bill

    # ---- 1. lavoro in parallelo -----------------------------------------------
    def test_01_parallel_day_splits_cost(self):
        task_a = self._order(self.pack).order_line.task_id
        task_b = self._order(self.pack).order_line.task_id
        line_a = self._ts(task_a, self.dev, 6)
        line_b = self._ts(task_b, self.dev, 6)
        # 12h segnate in una giornata da 8h: costo totale 8h x 35 = 280, non 420
        for line in (line_a, line_b):
            self.assertAlmostEqual(line.lab_parallel_ratio, 8 / 12, places=3)
            self.assertAlmostEqual(line.amount, -140, places=2)
            self.assertEqual(line.lab_parallel_state, "to_approve")
            self.assertEqual(line.unit_amount, 6, "Le ore fatturabili non cambiano")
        line_b.unlink()
        self.assertEqual(line_a.lab_parallel_state, "normal")
        self.assertAlmostEqual(line_a.lab_parallel_ratio, 1.0)
        self.assertAlmostEqual(line_a.amount, -210, places=2)

    def test_02_tm_parallel_hours_need_pm_approval(self):
        order = self._order(self.tm, 20)
        task_tm = order.order_line.task_id
        project_tm = task_tm.project_id
        self.assertEqual(project_tm._lab_contract_type(), "tm")
        other = self._order(self.pack).order_line.task_id
        self.assertEqual(other.project_id._lab_contract_type(), "corpo")
        line_tm = self._ts(task_tm, self.dev, 6)
        self._ts(other, self.dev, 6)
        self.assertEqual(line_tm.so_line, order.order_line)
        self.assertEqual(order.order_line.qty_delivered, 0,
                         "Ore parallele non approvate: non ancora fatturabili")
        with self.assertRaises(AccessError):
            line_tm.with_user(self.dev_user).action_lab_approve_parallel()
        line_tm.with_user(self.pm).action_lab_approve_parallel()
        self.assertEqual(line_tm.lab_parallel_state, "approved")
        self.assertEqual(order.order_line.qty_delivered, 6, "Approvate: si fatturano tutte")

    # ---- 2. consulenti esterni e pass-through ------------------------------------
    def test_03_consultant_accrual_bill_and_passthrough_tm(self):
        order = self._order(self.tm, 20)
        task = order.order_line.task_id
        project = task.project_id
        self.assertEqual(order.project_id, project)
        self.assertEqual(project.lab_passthrough_markup_pct, 15)
        line = self._ts(task, self.consultant, 8)
        self.assertEqual(line.amount, 0, "Nessun costo da dipendente per l'esterno")
        self.assertAlmostEqual(line.lab_accrued_external_cost, 400)  # 400 €/giorno
        self.assertFalse(line.so_line, "Su T&M le ore del consulente si ribaltano, non si fatturano a ore")
        self.env.flush_all()
        report = self.env["lab.margin.report"].search([("project_id", "=", project.id)])
        self.assertAlmostEqual(report.external_accrued, 400)
        self.assertAlmostEqual(report.external_cost, 400)
        # arriva la fattura: 8h x 55 = 440 (ha fatturato 40 € in più del maturato)
        bill = self._bill(project, 8, 55, self.consultant)
        bill_line = bill.invoice_line_ids
        self.assertEqual(line.lab_vendor_bill_line_id, bill_line)
        self.assertAlmostEqual(bill_line.lab_variance, 40)
        expense = order.order_line.filtered("is_expense")
        self.assertEqual(len(expense), 1, "La fattura del consulente va sull'ordine T&M")
        self.assertAlmostEqual(expense.price_unit, 63.25)  # 55 + 15%
        self.env.flush_all()
        self.env["lab.margin.report"].invalidate_model()
        report = self.env["lab.margin.report"].search([("project_id", "=", project.id)])
        self.assertAlmostEqual(report.external_accrued, 0)
        self.assertAlmostEqual(report.external_cost, 440)
        self.assertAlmostEqual(report.passthrough_cost, 440)
        self.assertAlmostEqual(report.passthrough_revenue, 506)
        self.assertAlmostEqual(report.margin, 506 - 440)
        self.assertAlmostEqual(report.margin_excl_passthrough, 0)
        # L-03: lo sconto sulla riga ribaltata vale anche nel report
        expense.discount = 10
        self.env.flush_all()
        self.env["lab.margin.report"].invalidate_model()
        report = self.env["lab.margin.report"].search([("project_id", "=", project.id)])
        self.assertAlmostEqual(report.passthrough_revenue, 506 * 0.9)

    def test_04_no_passthrough_on_fixed_price(self):
        order = self._order(self.pack)
        project = order.order_line.task_id.project_id
        self._bill(project, 8, 50, self.consultant)
        self.assertFalse(order.order_line.filtered("is_expense"),
                         "Contratto a corpo: il costo del consulente non si ribalta")
        self.env.flush_all()
        report = self.env["lab.margin.report"].search([("project_id", "=", project.id)])
        self.assertAlmostEqual(report.external_cost, 400)
        self.assertAlmostEqual(report.other_vendor_cost, 0)
        self.assertAlmostEqual(report.margin, 2750 - 400)
        # L-02: una fattura fornitore senza consulente va negli altri costi fornitori
        self._bill(project, 1, 120)
        self.env.flush_all()
        self.env["lab.margin.report"].invalidate_model()
        report = self.env["lab.margin.report"].search([("project_id", "=", project.id)])
        self.assertAlmostEqual(report.external_cost, 400)
        self.assertAlmostEqual(report.other_vendor_cost, 120)
        self.assertAlmostEqual(report.total_cost, 520)
        self.assertAlmostEqual(report.margin, 2750 - 520)

    def test_05_markup_zero_on_project(self):
        order = self._order(self.tm, 10)
        project = order.order_line.task_id.project_id
        project.lab_passthrough_markup_pct = 0
        self._bill(project, 4, 50)
        expense = order.order_line.filtered("is_expense")
        self.assertAlmostEqual(expense.price_unit, 50, msg="Ricarico 0% = al puro costo")

    # ---- 3. licenze AI --------------------------------------------------------------
    def test_06_ai_license_allocation_month(self):
        task_a = self._order(self.pack).order_line.task_id
        task_b = self._order(self.pack).order_line.task_id
        task_a.project_id.user_id = self.pm
        self.env["lab.ai.license"].create([
            {"employee_id": self.dev.id, "tool_id": self.env.ref(
                "lab_workflow_custom.ai_tool_claude_max").id, "monthly_cost": 100,
             "date_start": date(2020, 1, 1)},
            {"employee_id": self.pm_employee.id, "tool_id": self.env.ref(
                "lab_workflow_custom.ai_tool_claude_team").id, "monthly_cost": 30,
             "allocation_mode": "governance", "date_start": date(2020, 1, 1)},
        ])
        self.assertAlmostEqual(self.dev.lab_ai_monthly_cost, 100)
        std = self.env["hr.employee"]._lab_standard_month_hours()
        self.assertAlmostEqual(self.dev.lab_ai_hourly_uplift, 100 / std, places=4)
        self.assertAlmostEqual(self.dev.lab_fully_loaded_cost, 35 + 100 / std, places=2)
        # mese scorso (finito): 60h su A, 40h su B -> 60 € e 40 €
        last = self.day.replace(day=1) - timedelta(days=1)
        first_last = last.replace(day=1)
        for i in range(10):
            self._ts(task_a, self.dev, 6, first_last + timedelta(days=i))
        for i in range(5):
            self._ts(task_b, self.dev, 8, first_last + timedelta(days=i + 10))
        period = self.env["lab.cost.period"]._get_or_create(last)
        period.action_compute()
        dev_allocs = period.allocation_ids.filtered(lambda a: a.employee_id == self.dev)
        by_project = {a.project_id: a.amount for a in dev_allocs}
        self.assertAlmostEqual(by_project[task_a.project_id], 60)
        self.assertAlmostEqual(by_project[task_b.project_id], 40)
        # PM in governance: tutta la sua licenza sulla commessa di cui è PM
        pm_allocs = period.allocation_ids.filtered(lambda a: a.employee_id == self.pm_employee)
        self.assertEqual(pm_allocs.project_id, task_a.project_id)
        self.assertAlmostEqual(sum(pm_allocs.mapped("amount")), 30)
        # mese in corso: maggiorazione oraria, il resto resta nei costi generali
        self._ts(task_a, self.dev, 8)
        current = self.env["lab.cost.period"]._get_or_create(self.day)
        current.action_compute()
        allocs = current.allocation_ids.filtered(lambda a: a.employee_id == self.dev)
        on_a = sum(allocs.filtered(lambda a: a.project_id == task_a.project_id).mapped("amount"))
        self.assertAlmostEqual(on_a, 8 * 100 / std, places=2)
        self.assertAlmostEqual(sum(allocs.mapped("amount")), 100, places=2)
        self.env.flush_all()
        report = self.env["lab.margin.report"].search([("project_id", "=", task_b.project_id.id)])
        self.assertAlmostEqual(report.ai_cost, 40)
        # solo l'Amministrazione chiude il mese
        with self.assertRaises(Exception):
            period.with_user(self.pm).action_close()

    # ---- 4. pianificazione con fattore parallelo -----------------------------------
    def test_07_planning_parallel_factor(self):
        task = self._order(self.pack).order_line.task_id
        self.dev.lab_parallel_factor = 1.5
        monday = self.day - timedelta(days=self.day.weekday())
        Slot = self.env["lab.planning.slot"]
        slots = Slot.create([{"employee_id": self.dev.id, "project_id": task.project_id.id,
                              "date": monday + timedelta(days=d), "allocated_hours": 9.6}
                             for d in range(5)])  # 48h = 32 x 1,5
        # L-01: il turno mostra il limite reale della persona, non un 32h fisso
        self.assertAlmostEqual(slots[0].weekly_limit, 48)
        self.assertAlmostEqual(slots[0].weekly_factor, 1.5)
        self.assertAlmostEqual(slots[0].weekly_planned, 48)
        with self.assertRaises(ValidationError):
            Slot.create({"employee_id": self.dev.id, "project_id": task.project_id.id,
                         "date": monday, "allocated_hours": 1})
        # il PM riporta la settimana successiva a fattore 1,0: limite 32h
        next_monday = monday + timedelta(days=7)
        self.env["lab.planning.capacity"].create({
            "employee_id": self.dev.id, "week_start": next_monday + timedelta(days=2),
            "parallel_factor": 1.0})
        with self.assertRaises(ValidationError):
            Slot.create({"employee_id": self.dev.id, "project_id": task.project_id.id,
                         "date": next_monday, "allocated_hours": 33})
