"""Ticket di assistenza (Helpdesk OCA) collegati alle commesse.

- Il cliente apre il ticket via email, dal modulo web pubblico o dal portale.
- Il contatto si riconosce dall'email; la commessa a canone (AMS) del cliente si collega da sola,
  così le ore segnate sul ticket scalano il monte ore del mese e fanno scattare gli alert 75%/90%.
- Gli SLA guardano il tipo di contratto della commessa (campo ``lab_contract_type``).
"""
import base64
import binascii
import re
from datetime import timedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from .project_task import ALERT_LEVELS

# Immagini dentro la descrizione scritta sul sito (editor del modulo pubblico)
INLINE_IMAGE = re.compile(r'<img\b[^>]*?\ssrc="data:([^";,]+);base64,([^"]*)"[^>]*>', re.I)
INLINE_IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
                      "image/webp": "webp"}
INLINE_IMAGE_MAX = 10
INLINE_IMAGE_MAX_BYTES = 5 * 1024 * 1024

CONTRACT_TYPES = [("corpo", "A corpo / monte ore"), ("tm", "Time & Material"),
                  ("canone", "Canone ricorrente"), ("interno", "Interno (senza ordine)")]


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    lab_contract_type = fields.Selection(
        CONTRACT_TYPES, "Tipo contratto", compute="_compute_lab_contract",
        help="Tipo di contratto della commessa collegata: decide gli SLA applicati.")
    lab_hours_alert = fields.Selection(
        ALERT_LEVELS, "Alert monte ore", compute="_compute_lab_contract",
        help="Consumo del monte ore della commessa (per il canone AMS: mese corrente).")
    lab_consumption_pct = fields.Float("% monte ore", compute="_compute_lab_contract")

    @api.depends("project_id")
    def _compute_lab_contract(self):
        for ticket in self:
            project = ticket.project_id.sudo()
            if project:
                ticket.lab_contract_type = project._lab_contract_type()
                ticket.lab_hours_alert = project.lab_alert_level
                ticket.lab_consumption_pct = project.lab_consumption_pct
            else:
                ticket.lab_contract_type = False
                ticket.lab_hours_alert = "none"
                ticket.lab_consumption_pct = 0.0

    # ---- Contatto e commessa ------------------------------------------------------
    @api.model
    def _lab_partner_from_email(self, email):
        normalized = tools.email_normalize(email or "")
        if not normalized:
            return self.env["res.partner"]
        return self.env["res.partner"].sudo().search(
            [("email_normalized", "=", normalized)], order="id", limit=1)

    @api.model
    def _lab_find_project(self, partner):
        """Commessa a canone (AMS) attiva del cliente; se ce n'è più di una la più recente.
        Per gli altri contratti la commessa la sceglie il Supporto (serve anche il task)."""
        commercial = partner.commercial_partner_id
        if not commercial:
            return self.env["project.project"]
        projects = self.env["project.project"].sudo().search(
            [("partner_id", "child_of", commercial.id)], order="id desc")
        return projects.filtered(lambda p: p._lab_contract_type() == "canone")[:1]

    @api.model
    def _lab_default_team(self):
        return self.env.ref("lab_workflow_custom.helpdesk_team_support", raise_if_not_found=False)

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env["res.partner"]
        # Dal sito e dalle email il ticket lo crea l'utente tecnico (OdooBot/superutente):
        # senza questo, l'assegnatario predefinito sarebbe lui invece di "nessuno"
        system_user = self.env.su or self.env.user._is_public()
        for vals in vals_list:
            if system_user and "user_id" not in vals:
                vals["user_id"] = False
            if not vals.get("partner_id") and vals.get("partner_email"):
                vals["partner_id"] = self._lab_partner_from_email(vals["partner_email"]).id
            partner = Partner.browse(vals.get("partner_id")).sudo()
            if partner and not vals.get("partner_email"):
                vals["partner_email"] = partner.email
            if partner and not vals.get("partner_name"):
                vals["partner_name"] = partner.name
            if partner and not vals.get("project_id"):
                vals["project_id"] = self._lab_find_project(partner).id
            if not vals.get("team_id") and self._lab_default_team():
                vals["team_id"] = self._lab_default_team().id
            if self.env.context.get("lab_from_website") and not vals.get("channel_id"):
                vals["channel_id"] = self.env.ref("helpdesk_mgmt.helpdesk_ticket_channel_web").id
        tickets = super().create(vals_list)
        tickets._lab_subscribe_customer()
        if self.env.context.get("lab_from_website"):
            tickets._lab_store_inline_images()
        return tickets

    # ---- Descrizione dal modulo pubblico (editor con formattazione e immagini) ------
    def website_form_input_filter(self, request, values):
        """Hook standard di /website/form. Il form builder tratta i campi HTML come testo
        semplice; se la descrizione arriva dall'editor (flag lab_rich, vedi controllers) si usa
        l'HTML così com'è: lo ripulisce il campo stesso (sanitize: via script, eventi, link
        javascript:, immagini SVG)."""
        values = super().website_form_input_filter(request, values) \
            if hasattr(super(), "website_form_input_filter") else values
        raw = request.params.get("description")
        if self.env.context.get("lab_rich_description") and raw and raw.strip():
            values["description"] = tools.html_sanitize(raw, sanitize_style=True)
        return values

    def _lab_store_inline_images(self):
        """Le immagini incollate nella descrizione (data URI) diventano allegati del ticket:
        il testo resta leggero e le immagini si aprono anche dal link "Segui il ticket"."""
        Attachment = self.env["ir.attachment"].sudo()
        for ticket in self.sudo():
            description = ticket.description or ""
            if "data:" not in description:
                continue
            counter = {"n": 0}

            def replace(match, ticket=ticket, counter=counter):
                declared = match.group(1).lower()
                try:
                    data = base64.b64decode(match.group(2), validate=False)
                except (binascii.Error, ValueError):
                    return ""
                mimetype = guess_mimetype(data)
                if (declared not in INLINE_IMAGE_TYPES or mimetype not in INLINE_IMAGE_TYPES
                        or len(data) > INLINE_IMAGE_MAX_BYTES
                        or counter["n"] >= INLINE_IMAGE_MAX):
                    return ""  # tipo non ammesso, troppo grande o troppe: si scarta
                counter["n"] += 1
                attachment = Attachment.create({
                    "name": f"immagine_{counter['n']}.{INLINE_IMAGE_TYPES[mimetype]}",
                    "raw": data, "mimetype": mimetype,
                    "res_model": ticket._name, "res_id": ticket.id})
                token = attachment.generate_access_token()[0]
                return (f'<img src="/web/image/{attachment.id}?access_token={token}" '
                        f'class="img-fluid" alt="{attachment.name}">')

            new_description = INLINE_IMAGE.sub(replace, description)
            if new_description != description:
                ticket.description = new_description

    def write(self, vals):
        res = super().write(vals)
        if vals.get("partner_id"):
            for ticket in self.filtered(lambda t: not t.project_id):
                project = self._lab_find_project(ticket.partner_id.sudo())
                if project:
                    ticket.project_id = project
            self._lab_subscribe_customer()
        if {"partner_id", "project_id", "priority", "type_id", "category_id"} & set(vals):
            # Gli SLA dipendono da contratto e priorità: se cambiano si riallineano
            # (si aggiungono quelli nuovi, si tolgono quelli che non valgono più)
            for ticket in self.filtered(lambda t: t.team_id.use_sla and not t.closed):
                ticket.refresh_sla()
        return res

    def _lab_subscribe_customer(self):
        """Il cliente segue il ticket: riceve per email le risposte del Supporto."""
        for ticket in self.filtered("partner_id"):
            if ticket.partner_id not in ticket.message_partner_ids:
                ticket.sudo().message_subscribe(partner_ids=ticket.partner_id.ids)

    @api.onchange("partner_id")
    def _onchange_lab_partner_project(self):
        if self.partner_id and not self.project_id:
            self.project_id = self._lab_find_project(self.partner_id)

    @api.onchange("team_id")
    def _onchange_team_id(self):
        # OCA azzera la commessa se il team non ne ha una predefinita: la nostra la sceglie
        # il cliente, quindi la teniamo.
        kept = {ticket: ticket.project_id for ticket in self}
        res = super()._onchange_team_id()
        for ticket in self:
            if not ticket.project_id and not ticket.team_id.default_project_id:
                ticket.project_id = kept[ticket]
        return res

    # ---- Email sugli stadi (chiamato da data/helpdesk_mail_data.xml) --------------
    @api.model
    def _lab_setup_stage_templates(self):
        ref = self.env.ref
        oca_default = ref("helpdesk_mgmt.closed_ticket_template", raise_if_not_found=False)
        replaceable = self.env["mail.template"] | (oca_default or self.env["mail.template"])
        for stage_xmlid, template_xmlid in (
                ("helpdesk_ticket_stage_new", "mail_template_ticket_received"),
                ("helpdesk_ticket_stage_in_progress", "mail_template_ticket_in_progress"),
                ("helpdesk_ticket_stage_awaiting", "mail_template_ticket_awaiting"),
                ("helpdesk_ticket_stage_done", "mail_template_ticket_done")):
            stage = ref(f"helpdesk_mgmt.{stage_xmlid}", raise_if_not_found=False)
            template = ref(f"lab_workflow_custom.{template_xmlid}", raise_if_not_found=False)
            if stage and template and (not stage.mail_template_id
                                       or stage.mail_template_id in replaceable):
                stage.mail_template_id = template
        done = ref("helpdesk_mgmt.helpdesk_ticket_stage_done", raise_if_not_found=False)
        rating = ref("helpdesk_mgmt_rating.rating_ticket_email_template", raise_if_not_found=False)
        if done and rating and not done.rating_mail_template_id:
            done.rating_mail_template_id = rating

    # ---- Protezione del modulo web pubblico -------------------------------------
    @api.model
    def _lab_check_website_rate(self, email):
        """Massimo N ticket all'ora dallo stesso indirizzo (parametro di sistema)."""
        limit = int(self.env["ir.config_parameter"].sudo().get_param(
            "lab_workflow_custom.helpdesk_web_max_per_hour", 5))
        normalized = tools.email_normalize(email or "")
        if not normalized:
            raise UserError(_("Indica un indirizzo email valido: ti serve per seguire il ticket."))
        since = fields.Datetime.now() - timedelta(hours=1)
        recent = self.sudo().search_count([
            ("partner_email", "ilike", normalized), ("create_date", ">=", since),
            ("channel_id", "=", self.env.ref("helpdesk_mgmt.helpdesk_ticket_channel_web").id)])
        if recent >= limit:
            raise UserError(_("Hai già aperto molti ticket nell'ultima ora: riprova più tardi "
                              "oppure rispondi via email a un ticket già aperto."))
