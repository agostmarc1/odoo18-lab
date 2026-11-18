# -*- coding: utf-8 -*-
from odoo import fields, models

from .claude_service import DEFAULT_EFFORT, DEFAULT_MODEL


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Salvati come parametri di sistema (Impostazioni > Tecnico > Parametri di sistema),
    # leggibili solo dagli amministratori.
    lw_anthropic_api_key = fields.Char(
        "Chiave API Anthropic", config_parameter="langhe_wine_ai.anthropic_api_key")
    lw_claude_model = fields.Char(
        "Modello Claude", config_parameter="langhe_wine_ai.model", default=DEFAULT_MODEL)
    lw_claude_effort = fields.Selection(
        [("low", "Rapido"), ("medium", "Bilanciato"), ("high", "Accurato")],
        string="Livello di ragionamento", config_parameter="langhe_wine_ai.effort",
        default=DEFAULT_EFFORT)
