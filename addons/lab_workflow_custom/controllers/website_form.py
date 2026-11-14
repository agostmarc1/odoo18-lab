"""Modulo web pubblico "Apri un ticket": protezioni contro lo spam.

- campo esca nascosto (``lab_hp``): le persone non lo vedono e lo lasciano vuoto, i bot lo riempiono;
- massimo N ticket all'ora dallo stesso indirizzo email
  (parametro ``lab_workflow_custom.helpdesk_web_max_per_hour``, default 5);
- se in Impostazioni > Sito web si inseriscono le chiavi reCAPTCHA, Odoo verifica anche quelle
  (controllo standard di ``/website/form``, nessun codice qui).

La descrizione scritta con l'editor arriva come HTML (campo ``lab_rich=1``): la ripulisce
``helpdesk.ticket.website_form_input_filter`` e le immagini diventano allegati del ticket.
"""
import json

from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.website.controllers.form import WebsiteForm

HONEYPOT = "lab_hp"
RICH_FLAG = "lab_rich"


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
        # Descrizione scritta con l'editor (static/src/js/helpdesk_rich_description.js): è HTML,
        # non testo semplice. Il flag non deve finire nella descrizione come "altro campo".
        rich = bool(kwargs.pop(RICH_FLAG, ""))
        request.update_context(lab_from_website=True, lab_rich_description=rich)
        return super()._handle_website_form(model_name, **kwargs)
