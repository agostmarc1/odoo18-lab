# -*- coding: utf-8 -*-
from odoo import api, fields, models

DENOMINATION_LEVELS = [
    ("docg", "DOCG"),
    ("doc", "DOC"),
    ("igt", "IGT"),
    ("vino", "Vino (senza IG)"),
]


class LwWineDenomination(models.Model):
    """Denominazione di origine (es. Barolo DOCG, Langhe Nebbiolo DOC)."""

    _name = "lw.wine.denomination"
    _description = "Denominazione vino"
    _order = "level, name"

    name = fields.Char("Nome", required=True,
                       help="Nome della denominazione senza la sigla, es. 'Barolo'.")
    level = fields.Selection(DENOMINATION_LEVELS, string="Livello", required=True, default="doc")
    region = fields.Char("Zona / Regione", default="Piemonte")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_level_uniq", "unique(name, level)", "Questa denominazione esiste già."),
    ]

    @api.depends("name", "level")
    def _compute_display_name(self):
        labels = dict(DENOMINATION_LEVELS)
        for rec in self:
            suffix = labels.get(rec.level) if rec.level != "vino" else ""
            rec.display_name = " ".join(p for p in (rec.name, suffix) if p)


class LwWineGrape(models.Model):
    """Vitigno (es. Nebbiolo, Barbera, Dolcetto, Moscato bianco)."""

    _name = "lw.wine.grape"
    _description = "Vitigno"
    _order = "name"

    name = fields.Char("Vitigno", required=True)
    color = fields.Selection([("red", "Rosso"), ("white", "Bianco"), ("rose", "Rosato")],
                             string="Colore uva")
    active = fields.Boolean(default=True)

    _sql_constraints = [("name_uniq", "unique(name)", "Questo vitigno esiste già.")]
