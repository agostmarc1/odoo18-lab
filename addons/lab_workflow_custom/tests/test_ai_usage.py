from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

# Esempio di risposta di GET /v1/organizations/analytics/cost (forma documentata da Anthropic):
# importi in centesimi di USD con 6 decimali.
SAMPLE_PAYLOAD = {
    "data": [
        {"starting_at": "2026-09-03T00:00:00Z", "ending_at": "2026-09-04T00:00:00Z",
         "group": {"workspace_id": "wrkspc_T1", "api_key_id": "apikey_T1", "actor": None,
                   "product": None, "model": "claude-sonnet-5-5"},
         "cost": {"currency": "USD", "amount": "41280.000000", "list_amount": "51600.000000"}},
        {"starting_at": "2026-09-03T00:00:00Z", "ending_at": "2026-09-04T00:00:00Z",
         "group": {"workspace_id": None, "api_key_id": None,
                   "actor": {"type": "user_actor", "user_id": "user_T1"},
                   "product": "claude_code", "model": "claude-opus-5-5"},
         "cost": {"currency": "USD", "amount": "1250.500000"}},
    ],
    "has_more": False,
}


@tagged("post_install", "-at_install")
class TestLabAiUsage(TransactionCase):
    """Fase 2: consumi AI a consumo -> commesse (diretti, per persona, costi generali)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True,
                                       mail_notrack=True))
        cls.partner = cls.env["res.partner"].create({"name": "Cliente AI Srl"})
        cls.tm = cls.env.ref("lab_workflow_custom.product_tm_hourly").product_variant_id
        cls.pack = cls.env.ref("lab_workflow_custom.product_hours_pack_50").product_variant_id
        cls.dev = cls.env["hr.employee"].create({"name": "Dev AI", "hourly_cost": 35})
        cls.company_currency = cls.env.company.currency_id
        # un mese senza i dati sintetici (che chiudono il mese scorso)
        start = date.today().replace(day=1)
        for _i in range(3):
            start = (start - timedelta(days=1)).replace(day=1)
        cls.last_day = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        # il mese lo chiude l'Amministrazione, che non può modificare le ripartizioni a mano
        cls.accountant = new_test_user(
            cls.env, "ai_amm", groups="lab_workflow_custom.group_lab_amministrazione")
        cls.first_day = cls.last_day.replace(day=1)

    def _order(self, product, qty=1):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": qty})]})
        order.action_confirm()
        return order

    def _usage(self, amount, day=None, **refs):
        return self.env["lab.ai.usage"].create(dict({
            "date": day or self.first_day + timedelta(days=5), "amount_currency": amount,
            "currency_id": self.company_currency.id, "source": "manual"}, **refs))

    def test_01_parse_anthropic_payload(self):
        vals = self.env["lab.ai.usage"]._lab_parse_anthropic_rows(SAMPLE_PAYLOAD)
        self.assertEqual(len(vals), 2)
        self.assertAlmostEqual(vals[0]["amount_currency"], 412.80)
        self.assertEqual(vals[0]["workspace_ref"], "wrkspc_T1")
        self.assertEqual(vals[0]["date"], date(2026, 9, 3))
        self.assertEqual(vals[1]["actor_ref"], "user_T1")
        self.assertAlmostEqual(vals[1]["amount_currency"], 12.505)
        # reimportare la stessa riga aggiorna, non duplica
        Usage = self.env["lab.ai.usage"]
        self.assertEqual(Usage._lab_upsert(vals), (2, 0))
        vals[0]["amount_currency"] = 500
        self.assertEqual(Usage._lab_upsert(vals), (0, 2))
        self.assertEqual(Usage.search_count([("external_ref", "like", "anthropic|2026-09-03")]), 2)

    def test_02_connector_off_in_demo(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "lab_workflow_custom.anthropic_admin_key", False)
        with self.assertRaises(UserError):
            self.env["lab.ai.usage"].action_import_anthropic()
        self.env["lab.ai.usage"]._cron_import_anthropic()  # nessun errore, non fa nulla

    def test_03_mapping_and_allocation(self):
        # si parte senza i consumi demo (il test viene comunque annullato alla fine)
        self.env["lab.ai.usage"].search([]).unlink()
        order_tm = self._order(self.tm, 40)
        task_tm = order_tm.order_line.task_id
        project_tm = task_tm.project_id
        task_fix = self._order(self.pack).order_line.task_id
        # ore del mese scorso di Dev AI: 30h T&M, 10h a corpo
        for i in range(5):
            self.env["account.analytic.line"].create({
                "name": "x", "project_id": project_tm.id, "task_id": task_tm.id,
                "employee_id": self.dev.id, "unit_amount": 6,
                "date": self.first_day + timedelta(days=i)})
        self.env["account.analytic.line"].create({
            "name": "x", "project_id": task_fix.project_id.id, "task_id": task_fix.id,
            "employee_id": self.dev.id, "unit_amount": 10, "date": self.first_day + timedelta(days=6)})
        direct = self._usage(100, workspace_ref="wrkspc_TM")
        personal = self._usage(80, actor_ref="user_DEV")
        unknown = self._usage(20, api_key_ref="apikey_X")
        self.assertEqual(direct.attribution, "overhead", "Senza corrispondenze: costi generali")
        # le corrispondenze si applicano anche ai consumi già registrati
        self.env["lab.ai.mapping"].create([
            {"ref_type": "workspace", "name": "wrkspc_TM", "project_id": project_tm.id},
            {"ref_type": "actor", "name": "user_DEV", "employee_id": self.dev.id},
        ])
        self.assertEqual(direct.project_id, project_tm)
        self.assertEqual(direct.attribution, "direct")
        self.assertEqual(personal.attribution, "person")
        self.assertEqual(unknown.attribution, "overhead")

        period = self.env["lab.cost.period"]._get_or_create(self.last_day)
        period.action_compute()
        var = period.allocation_ids.filtered(lambda a: a.cost_type == "ai_variable")
        on_tm = sum(var.filtered(lambda a: a.project_id == project_tm).mapped("amount"))
        on_fix = sum(var.filtered(lambda a: a.project_id == task_fix.project_id).mapped("amount"))
        self.assertAlmostEqual(on_tm, 100 + 80 * 30 / 40)   # diretto + 75% dei consumi personali
        self.assertAlmostEqual(on_fix, 80 * 10 / 40)
        self.assertAlmostEqual(sum(var.filtered(lambda a: not a.project_id).mapped("amount")), 20)
        self.assertTrue(var.filtered(lambda a: a.project_id == project_tm and a.basis_pct == 100
                                     ).passthrough, "Diretto su T&M: da ribaltare")

        # chiusura del mese: i 100 diretti diventano spesa viva sull'ordine T&M (+15%)
        with self.assertRaises(AccessError):
            period.allocation_ids[:1].with_user(self.accountant).write({"amount": 0})
        period.with_user(self.accountant).action_close()
        expense = order_tm.order_line.filtered("is_expense")
        self.assertEqual(len(expense), 1)
        self.assertAlmostEqual(expense.price_unit, 115)
        self.assertEqual(expense.qty_delivered, 1, "La spesa viva è pronta da fatturare")
        self.assertFalse(self._order(self.pack).order_line.filtered("is_expense"))
        self.env.flush_all()
        report = self.env["lab.margin.report"].search([("project_id", "=", project_tm.id)])
        self.assertAlmostEqual(report.ai_cost, 160)
        self.assertAlmostEqual(report.passthrough_revenue, 115)
        self.assertAlmostEqual(report.passthrough_cost, 100)

        # riapertura (spesa non ancora fatturata): la spesa torna a zero, poi si richiude
        period.with_user(self.accountant).action_reopen()
        self.assertEqual(expense.qty_delivered, 0)
        period.with_user(self.accountant).action_close()
        self.assertEqual(len(order_tm.order_line.filtered("is_expense")), 1, "Nessun doppione")
        self.assertEqual(expense.qty_delivered, 1)
