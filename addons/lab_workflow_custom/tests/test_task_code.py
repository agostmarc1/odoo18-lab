"""Numero unico dei task (modulo OCA project_task_code, dipendenza dell'app)."""
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLabTaskCode(TransactionCase):

    def test_01_task_numbered_and_searchable(self):
        """Ogni task, anche creato da un analista o da un ordine, ha un numero unico T...
        che compare nel nome mostrato e si può cercare."""
        dev = new_test_user(self.env, "t_code_dev", groups="lab_workflow_custom.group_lab_team")
        project = self.env["project.project"].create({"name": "Progetto numeri"})
        a = self.env["project.task"].create({"name": "Analisi", "project_id": project.id})
        b = self.env["project.task"].with_user(dev).sudo(False).create(
            {"name": "Sviluppo", "project_id": project.id, "user_ids": [(4, dev.id)]})
        for task in a | b:
            self.assertTrue(task.code.startswith("T"), task.code)
            self.assertIn(f"[{task.code}]", task.display_name)
        self.assertNotEqual(a.code, b.code)
        found = self.env["project.task"].name_search(a.code)
        self.assertEqual([r[0] for r in found], [a.id])

    def test_02_default_tasks_from_order_numbered(self):
        """I task di default creati dalla conferma dell'ordine hanno tutti un numero diverso."""
        product = self.env.ref("lab_workflow_custom.product_hours_pack_50", raise_if_not_found=False)
        if not product:
            self.skipTest("prodotto monte ore non trovato")
        partner = self.env["res.partner"].create({"name": "Cliente numeri"})
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [(0, 0, {"product_id": product.product_variant_id.id, "product_uom_qty": 1})]})
        order.action_confirm()
        tasks = self.env["project.task"].search([("project_id.sale_order_id", "=", order.id)])
        self.assertTrue(tasks)
        self.assertEqual(len(set(tasks.mapped("code"))), len(tasks))
        self.assertFalse(tasks.filtered(lambda t: t.code in (False, "/")))
