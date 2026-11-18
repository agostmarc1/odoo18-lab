# -*- coding: utf-8 -*-
"""Scenario della cantina Bricco Rosso, cliente della software house (dati sintetici)."""
from odoo.tests import TransactionCase, tagged

MODULE = "lab_workflow_custom"


@tagged("post_install", "-at_install")
class TestWineryScenario(TransactionCase):

    def test_winery_customer_full_cycle(self):
        if not self.env.ref(f"{MODULE}.synth_order_rossi", raise_if_not_found=False):
            self.skipTest("scenario sintetico non caricato in questo database")
        demo = self.env["lab.demo.data"]
        demo._lab_load_winery()                       # aggiunge la cantina se manca
        self.assertFalse(demo._lab_load_winery(), "il caricamento deve essere idempotente")

        order = self.env.ref(f"{MODULE}.synth_order_bricco")
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.partner_id.name, "Cantina Bricco Rosso S.r.l. Agricola")
        self.assertEqual(order.opportunity_id.stage_id.is_won, True, "opportunità vinta")
        project = order.order_line.task_id.project_id
        self.assertEqual(project._lab_contract_type(), "corpo")
        self.assertEqual(project.user_id, self.env.ref(f"{MODULE}.user_marco"))

        lines = self.env["account.analytic.line"].search([("project_id", "=", project.id)])
        self.assertTrue(lines, "ore segnate sulla commessa")
        self.assertTrue(all(lines.mapped("task_id")), "a corpo: ogni ora ha il suo task")
        self.assertEqual(set(lines.mapped("lab_parallel_state")), {"normal"},
                         "il lavoro sulla cantina non crea ore parallele")
        carlo = self.env.ref(f"{MODULE}.user_carlo").employee_id
        self.assertIn(carlo, lines.employee_id, "il consulente sviluppa il modulo")

        usage = self.env["lab.ai.usage"].search([("external_ref", "=", "synth|bricco|1")])
        self.assertEqual(usage.project_id, project, "consumo API diretto sulla commessa")

        quote = self.env.ref(f"{MODULE}.synth_quote_bricco")
        self.assertEqual(quote.state, "draft", "canone di assistenza ancora da firmare")
