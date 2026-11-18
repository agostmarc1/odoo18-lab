# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import demo_analyzer

BOTTLE_FORMATS = [
    ("0.375", "Mezza 0,375 L"),
    ("0.5", "0,50 L"),
    ("0.75", "Bordolese / Albeisa 0,75 L"),
    ("1.5", "Magnum 1,5 L"),
    ("3.0", "Doppio Magnum / Jéroboam 3 L"),
    ("5.0", "Jéroboam 5 L"),
    ("6.0", "Imperiale / Mathusalem 6 L"),
]

SHEET_SCHEMA = {
    "type": "object",
    "properties": {
        "it": {"type": "string", "description": "Scheda in italiano"},
        "en": {"type": "string", "description": "Scheda in inglese"},
        "de": {"type": "string", "description": "Scheda in tedesco"},
    },
    "required": ["it", "en", "de"],
    "additionalProperties": False,
}

SHEET_SYSTEM_PROMPT = """Sei il copywriter tecnico di una cantina delle Langhe.
Scrivi una scheda tecnica e commerciale del vino in tre lingue (italiano, inglese, tedesco),
pensata per importatori, distributori e carte dei vini Ho.Re.Ca.

Regole:
- Usa SOLO i dati forniti nel blocco <dati_vino>. Non inventare punteggi, premi, tempi di
  affinamento, tipi di legno, rese o note di degustazione che non siano presenti.
- Se un dato manca, omettilo senza segnalarlo.
- Struttura di ogni lingua: titolo (denominazione + annata), 1 paragrafo di presentazione
  (massimo 70 parole), poi una lista "Dati tecnici" con i valori disponibili
  (denominazione, annata, vitigno, gradazione, formato, cartone), poi "Abbinamenti" solo se
  presenti nelle note del produttore.
- Tono: sobrio, professionale, territoriale. Niente superlativi vuoti.
- Testo semplice, senza markdown: righe separate da a capo, voci di elenco con "- ".
"""


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # --- Identità del vino -------------------------------------------------
    lw_is_wine = fields.Boolean("È un vino", help="Attiva la scheda Vino e i calcoli export.")
    lw_vintage = fields.Integer("Annata", help="Anno di vendemmia. Lasciare 0 per i vini senza annata (NV).")
    lw_denomination_id = fields.Many2one("lw.wine.denomination", string="Denominazione")
    lw_grape_id = fields.Many2one("lw.wine.grape", string="Vitigno prevalente")
    lw_grape_percent = fields.Float("% vitigno prevalente", default=100.0)
    lw_alcohol = fields.Float("Grado alcolico (% vol)", digits=(4, 1))
    lw_format = fields.Selection(BOTTLE_FORMATS, string="Formato", default="0.75")
    lw_volume_l = fields.Float("Volume (L)", digits=(6, 3), compute="_compute_lw_volume_l",
                               store=True, readonly=False,
                               help="Litri per bottiglia; proposto dal formato, modificabile.")
    lw_producer_notes = fields.Text(
        "Note del produttore",
        help="Vinificazione, affinamento, note di degustazione, abbinamenti. "
             "Sono l'unica fonte che Claude usa per la scheda tecnica, oltre ai dati sopra.",
    )

    # --- Logistica / Packing List -----------------------------------------
    lw_bottle_net_kg = fields.Float("Peso netto bottiglia (kg)", digits=(6, 3),
                                    help="Peso del solo vino contenuto.")
    lw_bottle_gross_kg = fields.Float("Peso lordo bottiglia (kg)", digits=(6, 3),
                                      help="Vino + vetro + tappo + capsula + etichetta.")
    lw_bottles_per_case = fields.Integer("Bottiglie per cartone", default=6)
    lw_case_tare_kg = fields.Float("Tara cartone vuoto (kg)", digits=(6, 3),
                                   help="Peso del cartone vuoto con alveari/separatori.")
    lw_case_gross_kg = fields.Float("Peso lordo cartone (kg)", digits=(6, 3),
                                    compute="_compute_lw_case", store=True)
    lw_case_length_cm = fields.Float("Lunghezza cartone (cm)")
    lw_case_width_cm = fields.Float("Larghezza cartone (cm)")
    lw_case_height_cm = fields.Float("Altezza cartone (cm)")
    lw_case_volume_m3 = fields.Float("Volume cartone (m³)", digits=(8, 4),
                                     compute="_compute_lw_case", store=True)

    # --- Schede generate da Claude ----------------------------------------
    lw_sheet_it = fields.Text("Scheda tecnica IT")
    lw_sheet_en = fields.Text("Technical sheet EN")
    lw_sheet_de = fields.Text("Technisches Datenblatt DE")

    @api.depends("lw_format")
    def _compute_lw_volume_l(self):
        for tmpl in self:
            tmpl.lw_volume_l = float(tmpl.lw_format) if tmpl.lw_format else 0.0

    @api.depends("lw_bottles_per_case", "lw_bottle_gross_kg", "lw_case_tare_kg",
                 "lw_case_length_cm", "lw_case_width_cm", "lw_case_height_cm")
    def _compute_lw_case(self):
        for tmpl in self:
            tmpl.lw_case_gross_kg = tmpl.lw_bottles_per_case * tmpl.lw_bottle_gross_kg + tmpl.lw_case_tare_kg
            tmpl.lw_case_volume_m3 = (
                tmpl.lw_case_length_cm * tmpl.lw_case_width_cm * tmpl.lw_case_height_cm / 1_000_000.0
            )

    @api.onchange("lw_bottle_gross_kg")
    def _onchange_lw_bottle_gross_kg(self):
        # Il peso standard di Odoo (usato da spedizioni e corrieri) segue il peso lordo bottiglia.
        if self.lw_is_wine and self.lw_bottle_gross_kg:
            self.weight = self.lw_bottle_gross_kg

    @api.constrains("lw_vintage")
    def _check_lw_vintage(self):
        this_year = fields.Date.today().year
        for tmpl in self:
            if tmpl.lw_vintage and not (1900 <= tmpl.lw_vintage <= this_year + 1):
                raise ValidationError(_("Annata non valida: %s.", tmpl.lw_vintage))

    @api.constrains("lw_bottles_per_case")
    def _check_lw_bottles_per_case(self):
        for tmpl in self:
            if tmpl.lw_is_wine and tmpl.lw_bottles_per_case < 1:
                raise ValidationError(_("Le bottiglie per cartone devono essere almeno 1."))

    # ------------------------------------------------------------------
    # Dati del vino in forma compatta (per Claude e per i report)
    # ------------------------------------------------------------------
    def _lw_wine_facts(self):
        self.ensure_one()
        return {
            "nome": self.name,
            "codice": self.default_code or "",
            "denominazione": self.lw_denomination_id.display_name or "",
            "annata": self.lw_vintage or "senza annata",
            "vitigno": (f"{self.lw_grape_id.name} {self.lw_grape_percent:g}%"
                        if self.lw_grape_id else ""),
            "gradazione_vol": self.lw_alcohol or "",
            "formato_litri": self.lw_volume_l or "",
            "bottiglie_per_cartone": self.lw_bottles_per_case or "",
            "note_produttore": self.lw_producer_notes or "",
        }

    def action_lw_generate_sheet(self):
        """Pulsante "Genera scheda IT/EN/DE con Claude"."""
        for tmpl in self:
            if not tmpl.lw_is_wine:
                raise UserError(_("'%s' non è segnato come vino.", tmpl.name))
            service = self.env["lw.claude.service"]
            demo = service._lw_is_demo()
            if demo:
                result = demo_analyzer.technical_sheet(tmpl._lw_wine_facts())
            else:
                facts = json.dumps(tmpl._lw_wine_facts(), ensure_ascii=False, indent=1)
                result = service._lw_call_json(
                    SHEET_SYSTEM_PROMPT,
                    f"<dati_vino>\n{facts}\n</dati_vino>",
                    SHEET_SCHEMA,
                    max_tokens=8000,
                )
            tmpl.write({
                "lw_sheet_it": result.get("it", "").strip(),
                "lw_sheet_en": result.get("en", "").strip(),
                "lw_sheet_de": result.get("de", "").strip(),
            })
            tmpl.message_post(body=_("Scheda tecnica IT/EN/DE generata in modalità demo (solo dati inseriti).")
                              if demo else _("Scheda tecnica IT/EN/DE generata con Claude."))
        return True
