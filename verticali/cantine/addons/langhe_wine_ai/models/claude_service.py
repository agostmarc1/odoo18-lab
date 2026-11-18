# -*- coding: utf-8 -*-
"""Unico punto di contatto con le API di Anthropic.

Tutte le funzioni del modulo passano da ``lw.claude.service._lw_call_json``:
così chiave, modello, gestione errori e log stanno in un posto solo, e nei
test basta sostituire questo metodo con una risposta finta (nessuna chiave
reale necessaria).

La risposta di Claude è vincolata a uno schema JSON tramite gli *structured
outputs* (``output_config.format``): il codice riceve sempre JSON valido e
non deve "indovinare" il formato del testo.
"""
import json
import logging
import os

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Modello predefinito: Claude Sonnet 5.5 (il Sonnet attuale; i modelli
# claude-3-5 / claude-3-7 sono stati ritirati). Si cambia da Impostazioni.
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "medium"

# Fallback lato server in caso di rifiuto del modello (stop_reason "refusal"):
# la richiesta viene ripetuta su un modello alternativo dentro la stessa chiamata.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {
    "claude-sonnet-5-5",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-fable-5-1",
    "claude-fable-5-2",
}

PARAM_KEY = "langhe_wine_ai.anthropic_api_key"
PARAM_MODEL = "langhe_wine_ai.model"
PARAM_EFFORT = "langhe_wine_ai.effort"
PARAM_FALLBACK = "langhe_wine_ai.use_fallback"


class LwClaudeService(models.AbstractModel):
    _name = "lw.claude.service"
    _description = "Langhe Wine AI - servizio Claude"

    @api.model
    def _lw_is_demo(self):
        """Modalità demo: nessuna chiave nei parametri né nell'ambiente del server.

        In demo il modulo non chiama Anthropic: usa le regole di ``demo_analyzer``
        (stesso formato di risposta). Basta inserire la chiave per passare a Claude.
        """
        key = self.env["ir.config_parameter"].sudo().get_param(PARAM_KEY)
        return not (key or os.environ.get("ANTHROPIC_API_KEY"))

    @api.model
    def _lw_get_client(self):
        try:
            import anthropic  # import ritardato: il modulo si carica anche senza libreria
        except ImportError as exc:
            raise UserError(_(
                "La libreria Python 'anthropic' non è installata sul server Odoo. "
                "Chiedere all'amministratore di installarla (pip install anthropic)."
            )) from exc
        api_key = self.env["ir.config_parameter"].sudo().get_param(PARAM_KEY) or None
        if not api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            raise UserError(_(
                "Chiave API di Anthropic mancante. Inserirla in Impostazioni > Vendite > "
                "Assistente Claude, oppure nella variabile d'ambiente ANTHROPIC_API_KEY del server."
            ))
        # api_key=None -> l'SDK legge ANTHROPIC_API_KEY dall'ambiente.
        return anthropic, anthropic.Anthropic(api_key=api_key, timeout=120.0, max_retries=2)

    @api.model
    def _lw_call_json(self, system_prompt, user_content, schema, max_tokens=16000):
        """Chiama Claude e restituisce un ``dict`` conforme a ``schema``.

        Solleva ``UserError`` con un messaggio comprensibile per l'utente in
        tutti i casi di errore (chiave errata, limiti, rete, rifiuto, JSON).
        """
        anthropic, client = self._lw_get_client()
        icp = self.env["ir.config_parameter"].sudo()
        model = icp.get_param(PARAM_MODEL) or DEFAULT_MODEL
        effort = icp.get_param(PARAM_EFFORT) or DEFAULT_EFFORT
        use_fallback = icp.get_param(PARAM_FALLBACK, "True") not in ("False", "0", "")

        request = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
            "output_config": {
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        try:
            if use_fallback and model in FALLBACK_MODELS:
                response = client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **request
                )
            else:
                response = client.messages.create(**request)
        except anthropic.AuthenticationError as exc:
            raise UserError(_("Chiave API di Anthropic non valida o scaduta.")) from exc
        except anthropic.PermissionDeniedError as exc:
            raise UserError(_("La chiave API non ha i permessi per il modello %s.", model)) from exc
        except anthropic.NotFoundError as exc:
            raise UserError(_("Modello Claude '%s' non trovato: controllare le Impostazioni.", model)) from exc
        except anthropic.RateLimitError as exc:
            raise UserError(_("Troppe richieste a Claude in questo momento: riprovare tra un minuto.")) from exc
        except anthropic.BadRequestError as exc:
            raise UserError(_("Richiesta rifiutata dalle API di Anthropic: %s", exc.message)) from exc
        except anthropic.APIStatusError as exc:
            raise UserError(_("Servizio Claude non disponibile (errore %s). Riprovare più tardi.", exc.status_code)) from exc
        except anthropic.APIConnectionError as exc:
            raise UserError(_("Impossibile raggiungere i server di Anthropic: controllare la connessione.")) from exc

        usage = getattr(response, "usage", None)
        _logger.info(
            "Claude %s: request_id=%s stop=%s input=%s output=%s",
            response.model, getattr(response, "_request_id", None), response.stop_reason,
            getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None),
        )
        if response.stop_reason == "refusal":
            raise UserError(_("Claude ha rifiutato di elaborare questo testo. Compilare l'ordine a mano."))
        if response.stop_reason == "max_tokens":
            raise UserError(_("Il testo è troppo lungo per un'unica analisi: dividerlo in più parti."))

        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise UserError(_("Claude non ha restituito alcun contenuto."))
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise UserError(_("Risposta di Claude non leggibile. Riprovare.")) from exc
