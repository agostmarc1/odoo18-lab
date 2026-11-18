# -*- coding: utf-8 -*-
"""Il modello di cartella cliente si carica su un Odoo qualsiasi, due volte senza doppioni."""
import os

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCustomerPackage(TransactionCase):

    def test_standard_settings(self):
        user = self.env.ref("base.group_user")
        for xmlid in ("product.group_product_pricelist", "stock.group_production_lot",
                      "product.group_stock_packaging"):
            self.assertIn(self.env.ref(xmlid), user.implied_ids, xmlid)
        self.assertTrue(self.env.ref("cantina_standard.pl_export_usa").currency_id.name == "USD")

    def test_load_template_folder_twice(self):
        folder = os.path.join(get_module_path("cantina_standard"), "modello_cliente")
        Package = self.env["cs.customer.package"]
        first = Package._cs_load(folder)
        second = Package._cs_load(folder)
        self.assertEqual(first["vini"], 4)
        self.assertEqual(first["clienti"], 2)
        self.assertEqual(sorted(first["utenti"]), ["commerciale", "magazzino", "titolare"])
        self.assertEqual(len(first["demo"]), 3, "preventivo, ordine confermato, degustazione")
        self.assertEqual(second["demo"], [], "la seconda volta non crea doppioni")

        barolo = Package._cs_ref("wine_bar20")
        self.assertEqual((barolo.lw_vintage, barolo.lw_denomination_id.name, barolo.lw_format),
                         (2020, "Barolo", "0.75"))
        self.assertEqual(barolo.tracking, "lot")
        self.assertEqual(barolo.product_variant_id.packaging_ids.qty, 6)
        self.assertEqual(barolo.product_variant_id.qty_available, 600 - 0)
        usa = self.env.ref("cantina_standard.pl_export_usa")
        self.assertEqual(usa._get_product_price(barolo.product_variant_id, 1.0), 34.0)

        importer = Package._cs_ref("partner_esempio_wine_import_llc")
        self.assertEqual(importer.property_product_pricelist, usa)
        quote = Package._cs_ref("demo_quote_email")
        self.assertEqual(quote.state, "draft")
        self.assertIn("Barolo 2020", quote.lw_raw_request)
        self.assertEqual(Package._cs_ref("demo_order_confirmed").state, "sale")
        self.assertEqual(len(Package._cs_ref("demo_event").registration_ids), 8)

        titolare = Package._cs_ref("user_titolare")
        self.assertTrue(titolare.has_group("sales_team.group_sale_manager"))
        self.assertTrue(Package._cs_ref("user_magazzino").has_group("stock.group_stock_user"))

    def test_demo_order_from_template_email(self):
        """Il preventivo dimostrativo si compila con la modalità demo (nessuna chiave API)."""
        folder = os.path.join(get_module_path("cantina_standard"), "modello_cliente")
        Package = self.env["cs.customer.package"]
        Package._cs_load(folder)
        self.env["ir.config_parameter"].sudo().set_param("langhe_wine_ai.anthropic_api_key", False)
        quote = Package._cs_ref("demo_quote_email")
        if not self.env["lw.claude.service"]._lw_is_demo():
            self.skipTest("chiave Anthropic nell'ambiente del server")
        quote.action_lw_analyze_order()
        qty = {l.product_id.default_code: l.product_uom_qty for l in quote.order_line}
        self.assertEqual(qty, {"BAR20": 18, "BAR23": 12})
