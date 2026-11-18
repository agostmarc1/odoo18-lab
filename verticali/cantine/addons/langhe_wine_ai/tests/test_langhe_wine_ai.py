# -*- coding: utf-8 -*-
"""Test del modulo senza chiave API: la chiamata a Claude è sostituita da una risposta finta."""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLangheWineAi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.barolo_den = cls.env.ref("langhe_wine_ai.den_barolo")
        cls.nebbiolo = cls.env.ref("langhe_wine_ai.grape_nebbiolo")
        common = {
            "is_storable": True,
            "tracking": "lot",
            "lw_is_wine": True,
            "lw_denomination_id": cls.barolo_den.id,
            "lw_grape_id": cls.nebbiolo.id,
            "lw_alcohol": 14.5,
            "list_price": 40.0,
        }
        cls.barolo_2020 = cls.env["product.template"].create(dict(
            common, name="Barolo 2020", default_code="BAR20", lw_vintage=2020, lw_format="0.75",
            lw_bottle_net_kg=0.75, lw_bottle_gross_kg=1.5, lw_bottles_per_case=6,
            lw_case_tare_kg=0.5, lw_case_length_cm=30, lw_case_width_cm=20, lw_case_height_cm=35,
        )).product_variant_id
        cls.barolo_magnum = cls.env["product.template"].create(dict(
            common, name="Barolo 2019 Magnum", default_code="BAR19M", lw_vintage=2019, lw_format="1.5",
            lw_bottle_net_kg=1.5, lw_bottle_gross_kg=2.9, lw_bottles_per_case=1,
        )).product_variant_id
        cls.partner = cls.env["res.partner"].create({"name": "NY Fine Wines Import LLC"})
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Export USA",
            "item_ids": [(0, 0, {
                "applied_on": "1_product",
                "product_tmpl_id": cls.barolo_2020.product_tmpl_id.id,
                "compute_price": "fixed",
                "fixed_price": 31.0,
            })],
        })
        stock = cls.env.ref("stock.warehouse0").lot_stock_id
        lot = cls.env["stock.lot"].create({"name": "L2020-01", "product_id": cls.barolo_2020.id})
        cls.env["stock.quant"]._update_available_quantity(cls.barolo_2020, stock, 60, lot_id=lot)

    def setUp(self):
        super().setUp()
        # Questi test simulano Claude vero; la modalità demo ha i suoi test in fondo.
        demo = patch.object(type(self.env["lw.claude.service"]), "_lw_is_demo", return_value=False)
        demo.start()
        self.addCleanup(demo.stop)

    def _order(self, text="Hi, please send 2 cases of Barolo 2020 and 3 magnums 2019. Thanks"):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "pricelist_id": self.pricelist.id,
            "lw_raw_request": text,
        })

    def _fake(self, lines, unmatched=None, doubts=None):
        return {
            "customer_language": "en",
            "lines": lines,
            "unmatched": unmatched or [],
            "doubts": doubts or [],
            "delivery_notes": "Delivery to New York by end of month, FOB Genova",
            "summary": "L'importatore chiede Barolo 2020 e magnum 2019.",
        }

    def _patch(self, result):
        return patch.object(type(self.env["lw.claude.service"]), "_lw_call_json", return_value=result)

    def test_analyze_creates_lines_with_pricelist_and_stock_checks(self):
        order = self._order()
        result = self._fake([
            {"product_id": self.barolo_2020.id, "requested_text": "2 cases of Barolo 2020",
             "quantity": 2, "unit": "casse", "confidence": "alta", "note": ""},
            {"product_id": self.barolo_magnum.id, "requested_text": "3 magnums 2019",
             "quantity": 3, "unit": "bottiglie", "confidence": "media", "note": "annata dedotta"},
            {"product_id": 999999, "requested_text": "1 case of Barbaresco 2016",
             "quantity": 1, "unit": "casse", "confidence": "bassa", "note": "annata non in catalogo"},
        ])
        with self._patch(result) as mocked:
            order.action_lw_analyze_order()
        # Il catalogo inviato a Claude contiene il prezzo del listino del cliente.
        user_content = mocked.call_args.args[1]
        self.assertIn('"prezzo_listino": 31.0', user_content)
        self.assertIn("L2020-01", user_content)
        self.assertIn("<richiesta_cliente>", user_content)

        lines = order.order_line
        self.assertEqual(len(lines), 2, "l'id inesistente non deve generare righe")
        barolo_line = lines.filtered(lambda l: l.product_id == self.barolo_2020)
        self.assertEqual(barolo_line.product_uom_qty, 12, "2 casse da 6 = 12 bottiglie")
        self.assertEqual(barolo_line.price_unit, 31.0, "il prezzo lo decide il listino di Odoo")
        self.assertTrue(all(lines.mapped("lw_ai_generated")))

        notes = str(order.lw_ai_notes)
        self.assertIn("Barbaresco 2016", notes)            # non trovato
        self.assertIn("annata dedotta", notes)             # dubbio di Claude
        self.assertIn("giacenza libera 0", notes)          # magnum senza giacenza
        self.assertNotIn("Barolo 2020: giacenza", notes)   # 60 disponibili >= 12
        self.assertTrue(order.lw_ai_analyzed_at)

    def test_rerun_replaces_only_ai_lines(self):
        order = self._order()
        self.env["sale.order.line"].create({"order_id": order.id, "product_id": self.barolo_magnum.id,
                                            "product_uom_qty": 1})
        line = {"product_id": self.barolo_2020.id, "requested_text": "6 btl", "quantity": 6,
                "unit": "bottiglie", "confidence": "alta", "note": ""}
        with self._patch(self._fake([line])):
            order.action_lw_analyze_order()
            order.action_lw_analyze_order()
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(len(order.order_line.filtered("lw_ai_generated")), 1)

    def test_guards(self):
        order = self._order(text="")
        with self.assertRaises(UserError):
            order.action_lw_analyze_order()
        order.lw_raw_request = "2 cases"
        order.order_line = [(0, 0, {"product_id": self.barolo_2020.id, "product_uom_qty": 6})]
        order.action_confirm()
        with self.assertRaises(UserError):
            order.action_lw_analyze_order()

    def test_export_totals(self):
        order = self._order()
        order.order_line = [
            (0, 0, {"product_id": self.barolo_2020.id, "product_uom_qty": 14}),
            (0, 0, {"product_id": self.barolo_magnum.id, "product_uom_qty": 2}),
        ]
        tmpl = self.barolo_2020.product_tmpl_id
        self.assertAlmostEqual(tmpl.lw_case_gross_kg, 9.5)        # 6 x 1,5 + 0,5
        self.assertAlmostEqual(tmpl.lw_case_volume_m3, 0.021)     # 30 x 20 x 35 cm
        self.assertEqual(order.lw_total_bottles, 16)
        self.assertEqual(order.lw_total_cases, 2 + 2)             # 14 = 2 cartoni + 2 sfuse; magnum 1 per cassa
        self.assertEqual(order.lw_loose_bottles, 2)
        self.assertEqual(order.lw_total_packages, 5)
        self.assertAlmostEqual(order.lw_total_liters, 14 * 0.75 + 2 * 1.5)
        self.assertAlmostEqual(order.lw_alcohol_liters, (14 * 0.75 + 2 * 1.5) * 0.145, delta=0.001)
        self.assertAlmostEqual(order.lw_gross_weight_kg, 2 * 9.5 + 2 * 1.5 + 2 * 2.9)
        self.assertAlmostEqual(order.lw_net_weight_kg, 14 * 0.75 + 2 * 1.5)
        self.assertIn("misure cartone", order.lw_export_warnings)  # magnum senza misure

        html, _fmt = self.env["ir.actions.report"]._render_qweb_html(
            "langhe_wine_ai.action_report_lw_packing_list", order.ids)
        self.assertIn(b"Packing List", html)
        self.assertIn(b"BAR20", html)

    def test_generate_sheet(self):
        tmpl = self.barolo_2020.product_tmpl_id
        tmpl.lw_producer_notes = "Affinamento 24 mesi in botte grande di rovere di Slavonia."
        fake = {"it": "Barolo DOCG 2020 ...", "en": "Barolo DOCG 2020 ...", "de": "Barolo DOCG 2020 ..."}
        with self._patch(fake) as mocked:
            tmpl.action_lw_generate_sheet()
        self.assertIn("botte grande", mocked.call_args.args[1])
        self.assertEqual(tmpl.lw_sheet_de, "Barolo DOCG 2020 ...")

    def test_missing_key_message(self):
        self.env["ir.config_parameter"].sudo().set_param("langhe_wine_ai.anthropic_api_key", False)
        with patch.dict("os.environ", {}, clear=True):
            try:
                import anthropic  # noqa: F401
            except ImportError:
                return  # senza libreria il messaggio è diverso, verificato altrove
            with self.assertRaisesRegex(UserError, "Chiave API"):
                self.env["lw.claude.service"]._lw_get_client()

    # ------------------------------------------------------------------
    # Modalità demo: nessuna chiave, nessuna chiamata ad Anthropic
    # ------------------------------------------------------------------
    def test_demo_mode_without_key(self):
        from odoo.addons.langhe_wine_ai.models.claude_service import LwClaudeService
        service = self.env["lw.claude.service"]
        icp = self.env["ir.config_parameter"].sudo()
        with patch.dict("os.environ", {}, clear=True):
            icp.set_param("langhe_wine_ai.anthropic_api_key", False)
            self.assertTrue(LwClaudeService._lw_is_demo(service), "senza chiave: demo")
            icp.set_param("langhe_wine_ai.anthropic_api_key", "chiave-finta-di-test")
            self.assertFalse(LwClaudeService._lw_is_demo(service), "con la chiave: Claude")

    def test_demo_analysis_of_messy_email(self):
        Tmpl = self.env["product.template"]
        nebbiolo_den = self.env.ref("langhe_wine_ai.den_langhe_nebbiolo")
        langhe_nebbiolo = Tmpl.create({
            "name": "Langhe Nebbiolo 2023", "lw_is_wine": True, "lw_vintage": 2023,
            "lw_denomination_id": nebbiolo_den.id, "lw_format": "0.75", "list_price": 18,
        }).product_variant_id
        Tmpl.create({
            "name": "Barbaresco 2021", "lw_is_wine": True, "lw_vintage": 2021, "list_price": 35,
            "lw_denomination_id": self.env.ref("langhe_wine_ai.den_barbaresco").id,
        })
        email = ("hi Marco!! ok so pls send 5 cs of the Barolo 2020, also 2 cases nebbiolo "
                 "(the langhe one) and 6 magnums of barolo 19 if u still have them. my partner "
                 "asks also for a Barbaresco 2016, do u have?? price for the barolo was $31 right? "
                 "FOB Genova, need it in NY before April 15. cheers, Dave")
        order = self._order(text=email)
        with patch.object(type(self.env["lw.claude.service"]), "_lw_is_demo", return_value=True),                 patch.object(type(self.env["lw.claude.service"]), "_lw_call_json") as claude:
            order.action_lw_analyze_order()
        claude.assert_not_called()
        qty = {l.product_id: l.product_uom_qty for l in order.order_line}
        self.assertEqual(qty, {self.barolo_2020: 30, langhe_nebbiolo: 12, self.barolo_magnum: 6},
                         "5 cartoni = 30, 2 cartoni = 12, 6 magnum")
        notes = str(order.lw_ai_notes)
        self.assertIn("Modalità demo", notes)
        self.assertIn("annata 2016 non in catalogo", notes)
        self.assertIn("$31", notes)                       # prezzo citato da verificare
        self.assertIn("FOB Genova", notes)                # condizioni di consegna
        self.assertIn("giacenza libera 0", notes)         # magnum senza giacenza
        self.assertIn("EN", notes)

    def test_demo_german_order_and_sheet(self):
        order = self._order(text="Hallo, bitte 3 Kisten Barolo 2020 und 2 Flaschen Barolo Magnum 2019. Danke")
        with patch.object(type(self.env["lw.claude.service"]), "_lw_is_demo", return_value=True):
            order.action_lw_analyze_order()
            tmpl = self.barolo_2020.product_tmpl_id
            tmpl.action_lw_generate_sheet()
        qty = {l.product_id: l.product_uom_qty for l in order.order_line}
        self.assertEqual(qty, {self.barolo_2020: 18, self.barolo_magnum: 2})
        self.assertIn("DE", str(order.lw_ai_notes))
        self.assertIn("Jahrgang: 2020", tmpl.lw_sheet_de)
        self.assertIn("Alcohol: 14.5% vol", tmpl.lw_sheet_en)
        self.assertNotIn("premi", tmpl.lw_sheet_it.lower())  # nessun dato inventato
