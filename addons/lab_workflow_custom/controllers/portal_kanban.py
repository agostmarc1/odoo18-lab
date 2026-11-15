"""Portale clienti: Kanban dei ticket (/my/tickets/kanban).

- I ticket si leggono con l'utente collegato (mai sudo): la separazione per azienda la garantiscono
  le regole di sicurezza (OCA + regola globale ``rule_helpdesk_ticket_portal_company``).
- ``?fragment=1`` restituisce solo la bacheca: la usa static/src/js/portal_ticket_kanban.js per
  aggiornarsi quando arriva un avviso in tempo reale (bus) o ogni 60 secondi.
"""
from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..models.helpdesk_ticket import PORTAL_COLUMNS

SCOPES = ("company", "mine")
COLUMN_HINTS = {
    "supplier": "Il nostro team sta gestendo la richiesta: non devi fare nulla.",
    "customer": "Ci serve una tua risposta o un aggiornamento: apri il ticket e scrivici.",
    "resolved": "Richieste concluse.",
}


class LabPortalTicketKanban(CustomerPortal):

    @http.route("/my/tickets/kanban", type="http", auth="user", website=True)
    def lab_portal_tickets_kanban(self, scope="company", fragment=None, **kwargs):
        Ticket = request.env["helpdesk.ticket"]
        if not Ticket.has_access("read"):
            return request.redirect("/my")
        if scope not in SCOPES:
            scope = "company"
        domain = []
        if scope == "mine":
            domain = [("partner_id", "=", request.env.user.partner_id.id)]
        tickets = Ticket.search(domain, order="priority desc, last_stage_update desc, id desc")
        # Colonne pensate per il cliente: chi deve agire (fornitore, cliente) o risolto.
        # La fase interna resta visibile sulla scheda; "Risolto" parte chiusa (il cliente la apre).
        columns = []
        for key, label in PORTAL_COLUMNS:
            col_tickets = tickets.filtered(lambda t, k=key: t.stage_id.lab_portal_column == k)
            columns.append({"key": key, "name": label, "tickets": col_tickets,
                            "hint": COLUMN_HINTS[key], "folded": key == "resolved"})
        values = {
            "columns": columns,
            "scope": scope,
            "ticket_count": len(tickets),
            "page_name": "lab_ticket_kanban",
        }
        if fragment:
            return request.render("lab_workflow_custom.portal_ticket_kanban_board", values)
        values.update(self._prepare_portal_layout_values())
        values["page_name"] = "lab_ticket_kanban"
        return request.render("lab_workflow_custom.portal_my_tickets_kanban", values)
