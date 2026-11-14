"""Modulo web pubblico "Apri un ticket": protezioni contro lo spam.

- campo esca nascosto (``lab_hp``): le persone non lo vedono e lo lasciano vuoto, i bot lo riempiono;
- massimo N ticket all'ora dallo stesso indirizzo email
  (parametro ``lab_workflow_custom.helpdesk_web_max_per_hour``, default 5);
- se in Impostazioni > Sito web si inseriscono le chiavi reCAPTCHA, Odoo verifica anche quelle
  (controllo standard di ``/website/form``, nessun codice qui).
"""
import json

from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.website.controllers.form import WebsiteForm

HONEYPOT = "lab_hp"


class LabWebsiteForm(WebsiteForm):

    def _handle_website_form(self, model_name, **kwargs):
        if model_name != "helpdesk.ticket":
            return super()._handle_website_form(model_name, **kwargs)
        if kwargs.pop(HONEYPOT, ""):
            # Risposta neutra: al bot non diciamo che è stato riconosciuto
            return json.dumps({"id": False})
        try:
            request.env["helpdesk.ticket"]._lab_check_website_rate(kwargs.get("partner_email"))
        except UserError as error:
            return json.dumps({"error": error.args[0]})
        request.update_context(lab_from_website=True)
        return super()._handle_website_form(model_name, **kwargs)
