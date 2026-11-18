# -*- coding: utf-8 -*-
"""Soluzione di settore (Soluzione Cantina): offerta standard, installazioni e cruscotto."""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

MODULE = "lab_workflow_custom"


@tagged("post_install", "-at_install")
class TestVertical(TransactionCase):

    def setUp(self):
        super().setUp()
        if not self.env.ref(f"{MODULE}.synth_order_rossi", raise_if_not_found=False):
            self.skipTest("scenario sintetico non caricato in questo database")
        demo = self.env["lab.demo.data"]
        demo._lab_load_winery()
        demo._lab_load_vertical()
        self.assertFalse(demo._lab_load_vertical(), "il caricamento deve essere idempotente")
        self.vertical = self.env.ref(f"{MODULE}.synth_vertical_cantina")
        self.giuseppe = self.env.ref(f"{MODULE}.user_giuseppe")

    def test_dashboard_pilot_and_pipeline(self):
        vertical = self.vertical
        self.assertEqual(vertical.install_count, 1, "Bricco Rosso è la prima installazione")
        self.assertEqual(vertical.customer_count, 1)
        self.assertEqual(vertical.standard_hours, 60)
        self.assertEqual(vertical.pilot_hours, 120)
        self.assertEqual(vertical.hours_saved, 60, "ogni nuova cantina costa 60 h in meno")
        self.assertEqual(vertical.pipeline_count, 1, "Collina dei Noci in trattativa")
        self.assertEqual(vertical.pipeline_amount, 9000 + 12 * 450)
        pilot = vertical.project_ids
        self.assertEqual(pilot.partner_id, self.env.ref(f"{MODULE}.synth_partner_bricco"))
        self.assertEqual(pilot.lab_instance_url, "http://127.0.0.1:8070")
        ams = self.env.ref(f"{MODULE}.synth_product_cantina_ams").product_variant_id
        self.assertIn(ams, self.env.ref(f"{MODULE}.synth_quote_bricco").order_line.product_id,
                      "il canone di Bricco Rosso è quello standard del settore")
        self.assertGreater(vertical.revenue, 0)
        canone = self.env.ref(f"{MODULE}.synth_quote_noci_ams")
        self.assertEqual(canone.order_line.product_id, ams, "canone in un preventivo a parte")

    def test_standard_offer_creates_project_from_template(self):
        offer = self.env.ref(f"{MODULE}.synth_quote_noci")
        self.assertEqual(offer.state, "draft")
        offer.with_user(self.giuseppe).action_confirm()
        setup_line = offer.order_line.filtered(lambda l: l.product_id.default_code == "CANT-SETUP")
        project = setup_line.project_id
        self.assertTrue(project, "il setup standard crea la commessa")
        self.assertEqual(project.lab_vertical_id, self.vertical)
        self.assertEqual(project._lab_contract_type(), "corpo")
        template = self.env.ref(f"{MODULE}.synth_project_template_cantina")
        self.assertEqual(sorted(project.task_ids.mapped("name")), sorted(template.task_ids.mapped("name")),
                         "le fasi arrivano dal modello di progetto")
        self.assertEqual(sum(project.task_ids.mapped("allocated_hours")), 60)
        self.assertEqual(project.allocated_hours, 60)
        self.assertTrue(all(t.sale_line_id == setup_line for t in project.task_ids))
        self.assertFalse(template.lab_vertical_id, "il modello non conta come installazione")

        self.vertical.invalidate_recordset()
        self.assertEqual(self.vertical.install_count, 2)
        self.assertEqual(self.vertical.customer_count, 2)
        self.assertEqual(self.vertical.avg_sold_hours, (120 + 60) / 2)

    def test_economics_only_for_pm_and_administration(self):
        vertical = self.vertical.with_user(self.giuseppe)
        self.assertEqual(vertical.pipeline_count, 1, "il Commerciale vede le trattative")
        with self.assertRaises(AccessError):
            vertical.read(["margin"])
        marco = self.env.ref(f"{MODULE}.user_marco")
        self.assertTrue(self.vertical.with_user(marco).read(["margin_pct"]))
