"""Modulo web pubblico "Apri un ticket": protezioni contro lo spam.

- campo esca nascosto (``lab_hp``): le persone non lo vedono e lo lasciano vuoto, i bot lo riempiono;
- massimo N ticket all'ora dallo stesso indirizzo email
  (parametro ``lab_workflow_custom.helpdesk_web_max_per_hour``, default 5);
- se in Impostazioni > Sito web si inseriscono le chiavi reCAPTCHA, Odoo verifica anche quelle
  (controllo standard di ``/website/form``, nessun codice qui).

La descrizione scritta con l'editor arriva come HTML (campo ``lab_rich=1``): la ripulisce
``helpdesk.ticket.website_form_input_filter`` e le immagini diventano allegati del ticket.

Conferma via email: il ticket dal sito nasce "da confermare" (tranne per l'utente collegato che
usa la propria email); ``/assistenza/conferma/<id>/<codice>`` lo conferma e lo collega all'azienda.
"""
import json

from odoo import http, tools
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
        request.update_context(lab_from_website=True, lab_rich_description=rich,
                               lab_web_trusted=self._lab_is_own_email(kwargs.get("partner_email")))
        return super()._handle_website_form(model_name, **kwargs)

    @staticmethod
    def _lab_is_own_email(email):
        """Utente collegato (portale o interno) che scrive con la propria email: è già
        identificato, non serve la conferma via email."""
        user = request.env.user
        if not request.session.uid or user._is_public():
            return False
        own = tools.email_normalize(user.partner_id.email or "")
        return bool(own) and own == tools.email_normalize(email or "")

    @http.route("/assistenza/conferma/<int:ticket_id>/<string:token>", type="http",
                auth="public", website=True, sitemap=False)
    def lab_helpdesk_confirm(self, ticket_id, token, **kwargs):
        """Link dell'email "Conferma la tua richiesta"."""
        ticket = request.env["helpdesk.ticket"]._lab_check_confirm_token(ticket_id, token)
        if ticket:
            ticket._lab_web_confirm()
        return request.render("lab_workflow_custom.helpdesk_page_confirmed_view", {
            "ticket": ticket,
            "portal_url": ticket.get_portal_url() if ticket else False,
        })
