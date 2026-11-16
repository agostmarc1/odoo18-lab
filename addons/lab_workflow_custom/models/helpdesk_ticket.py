"""Ticket di assistenza (Helpdesk OCA) collegati alle commesse.

- Il cliente apre il ticket via email, dal modulo web pubblico o dal portale.
- Il contatto si riconosce dall'email; la commessa a canone (AMS) del cliente si collega da sola,
  così le ore segnate sul ticket scalano il monte ore del mese e fanno scattare gli alert 75%/90%.
- Gli SLA guardano il tipo di contratto della commessa (campo ``lab_contract_type``).
- Dal modulo pubblico il ticket nasce "da confermare": il cliente riceve un'email con il link di
  conferma e solo dopo il ticket si collega all'azienda (chi scrive un'email altrui non può
  aprire ticket a nome di quel cliente né consumare il suo monte ore).
"""
import base64
import binascii
import re
import secrets
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

# Campi che il cliente vede nel Kanban del portale: se cambiano, la sua bacheca si aggiorna
PORTAL_FIELDS = {"stage_id", "name", "priority", "partner_id", "user_id", "type_id", "active",
                 "lab_web_confirmed"}

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
    lab_web_confirmed = fields.Boolean(
        "Richiesta confermata", default=True, copy=False, index=True,
        help="Falso per i ticket aperti dal sito finché il cliente non clicca il link di "
             "conferma ricevuto per email: fino ad allora il ticket non è collegato all'azienda.")
    lab_confirm_token = fields.Char(copy=False, groups="base.group_system")

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
        # Dal sito, se chi scrive non è un utente collegato con quella stessa email
        # (lab_web_trusted, vedi controllers), il ticket aspetta la conferma via email
        to_confirm = (self.env.context.get("lab_from_website")
                      and not self.env.context.get("lab_web_trusted"))
        for vals in vals_list:
            if system_user and "user_id" not in vals:
                vals["user_id"] = False
            if to_confirm and not vals.get("partner_id"):
                vals.update(lab_web_confirmed=False, lab_confirm_token=secrets.token_urlsafe(32))
            # finché non conferma, nessun collegamento a contatto e commessa
            if (vals.get("lab_web_confirmed", True) and not vals.get("partner_id")
                    and vals.get("partner_email")):
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
        tickets.filtered(lambda t: not t.lab_web_confirmed)._lab_send_confirmation()
        tickets._lab_notify_portal()
        return tickets

    # ---- Conferma via email dei ticket aperti dal sito ------------------------------
    def set_sla(self):
        # Gli SLA partono dalla conferma (vedi _lab_web_confirm)
        return super(HelpdeskTicket, self.filtered("lab_web_confirmed")).set_sla()

    def _track_template(self, tracking):
        res = super()._track_template(tracking)
        if not self[0].lab_web_confirmed:
            res.pop("stage_id", None)  # al posto di "ricevuto" parte l'email di conferma
        return res

    def _lab_confirm_url(self):
        self.ensure_one()
        return (f"{self.get_base_url()}/assistenza/conferma/{self.id}/"
                f"{self.sudo().lab_confirm_token}")

    def _lab_send_confirmation(self):
        template = self.env.ref("lab_workflow_custom.mail_template_ticket_confirm",
                                raise_if_not_found=False)
        for ticket in self:
            # Una sola email di conferma per indirizzo: se ce n'è già una in attesa non se ne
            # mandano altre (il suo link conferma tutte le richieste). Così nessuno può usare il
            # modulo per inondare di email l'indirizzo di un altro, e il cliente non ha limiti.
            if ticket._lab_pending_same_email():
                ticket.message_post(body=_("Email di conferma non rinviata: per %s ce n'è già una "
                                           "in attesa, che conferma anche questa richiesta.",
                                           ticket.partner_email), subtype_xmlid="mail.mt_note")
                continue
            if template and ticket.partner_email:
                # il link con il codice passa dal contesto: il codice non è leggibile dai template
                template.sudo().with_context(lab_confirm_url=ticket._lab_confirm_url()).send_mail(
                    ticket.id, email_layout_xmlid="mail.mail_notification_light")

    @api.model
    def _lab_check_confirm_token(self, ticket_id, token):
        """Ticket da confermare con quel codice (confronto a tempo costante), oppure vuoto."""
        ticket = self.sudo().with_context(active_test=False).browse(ticket_id).exists()
        if (ticket and not ticket.lab_web_confirmed and ticket.active and token
                and ticket.lab_confirm_token
                and secrets.compare_digest(ticket.lab_confirm_token, token)):
            return ticket
        return self.browse()

    def _lab_web_confirm(self):
        """Il cliente ha cliccato il link (o il Supporto conferma a mano): il ticket si collega
        al contatto e alla commessa, partono gli SLA e l'email "Abbiamo ricevuto"."""
        for ticket in self.sudo().filtered(lambda t: not t.lab_web_confirmed):
            ticket.write({"lab_web_confirmed": True, "lab_confirm_token": False})
            partner = ticket._lab_partner_from_email(ticket.partner_email)
            if partner and not ticket.partner_id:
                ticket.partner_id = partner  # write: commessa AMS e cliente follower
            ticket.set_sla()
            ticket.ticket_sla_ids.write({"last_state_date": fields.Datetime.now()})
            template = ticket.stage_id.mail_template_id
            if template:
                template.send_mail(ticket.id, email_layout_xmlid="mail.mail_notification_light")
            ticket.message_post(body=_("Richiesta confermata dal cliente tramite il link "
                                       "ricevuto all'indirizzo %s.", ticket.partner_email),
                                subtype_xmlid="mail.mt_note")
            # lo stesso link conferma anche le altre richieste in attesa dallo stesso indirizzo
            ticket._lab_pending_same_email()._lab_web_confirm()
        return True

    def action_lab_web_confirm(self):
        """Pulsante del Supporto: conferma a mano (es. il cliente ha telefonato)."""
        if not self.env.user.has_group("helpdesk_mgmt.group_helpdesk_user"):
            raise UserError(_("Solo il Supporto può confermare una richiesta."))
        return self._lab_web_confirm()

    @api.model
    def _lab_archive_unconfirmed(self):
        """Cron: i ticket mai confermati dopo N giorni si archiviano (spam o errori)."""
        days = int(self.env["ir.config_parameter"].sudo().get_param(
            "lab_workflow_custom.helpdesk_web_confirm_days", 7))
        old = self.sudo().search([("lab_web_confirmed", "=", False),
                                  ("create_date", "<", fields.Datetime.now() - timedelta(days=days))])
        old.write({"active": False, "lab_confirm_token": False})
        return len(old)

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
        notify = bool(PORTAL_FIELDS & set(vals))
        before = self.sudo().mapped("commercial_partner_id") if notify else None
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
            for ticket in self.filtered(
                    lambda t: t.team_id.use_sla and not t.closed and t.lab_web_confirmed):
                ticket.refresh_sla()
        if notify:
            self._lab_notify_portal(before)
        return res

    # ---- Portale: Kanban aggiornato in tempo reale ---------------------------------
    def _lab_notify_portal(self, extra_companies=None):
        """Avviso istantaneo (bus) agli utenti portale dell'azienda del ticket: la loro bacheca
        Kanban si ricarica. Il messaggio contiene solo gli id: i dati li rilegge la pagina con i
        permessi del cliente. Le altre aziende non ricevono nulla."""
        tickets = self.sudo()
        companies = tickets.mapped("commercial_partner_id") | (extra_companies or self.env["res.partner"])
        if not companies:
            return
        users = self.env["res.users"].sudo().search([
            ("share", "=", True), ("partner_id.commercial_partner_id", "in", companies.ids)])
        for user in users:
            company = user.partner_id.commercial_partner_id
            ids = tickets.filtered(lambda t, c=company: t.commercial_partner_id == c).ids
            user.partner_id._bus_send("lab_ticket_update", {"ticket_ids": ids})

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
    def _lab_check_website_email(self, email):
        """Email obbligatoria e valida. Nessun limite al numero di ticket: il cliente ne apre
        quanti vuole (la protezione è sulle email di conferma, vedi _lab_send_confirmation)."""
        if not tools.email_normalize(email or ""):
            raise UserError(_("Indica un indirizzo email valido: ti serve per seguire il ticket."))

    def _lab_pending_same_email(self):
        """Altri ticket dal sito ancora da confermare con lo stesso indirizzo."""
        self.ensure_one()
        email = tools.email_normalize(self.partner_email or "")
        return self.sudo().search([
            ("id", "!=", self.id), ("lab_web_confirmed", "=", False),
            ("partner_email", "=ilike", email)]) if email else self.browse()


# Colonne del Kanban del portale: il cliente non vede le fasi interne, vede chi deve agire
PORTAL_COLUMNS = [("supplier", "Ci stiamo lavorando"), ("customer", "Serve un tuo riscontro"),
                  ("resolved", "Risolto")]


class HelpdeskTicketStage(models.Model):
    _inherit = "helpdesk.ticket.stage"

    lab_portal_column = fields.Selection(
        PORTAL_COLUMNS, string="Colonna nel portale",
        help="In quale colonna il cliente vede i ticket in questa fase, nel Kanban del portale: "
             "il fornitore ci lavora, serve un riscontro del cliente, oppure è risolto.")

    @api.model
    def _lab_init_portal_columns(self):
        """Colonna di base per le fasi che non ne hanno ancora una (anche quelle nuove)."""
        awaiting = self.env.ref("helpdesk_mgmt.helpdesk_ticket_stage_awaiting",
                                raise_if_not_found=False)
        for stage in self.with_context(active_test=False).search([("lab_portal_column", "=", False)]):
            if stage == awaiting:
                stage.lab_portal_column = "customer"
            else:
                stage.lab_portal_column = "resolved" if stage.closed else "supplier"

    @api.model_create_multi
    def create(self, vals_list):
        stages = super().create(vals_list)
        stages.filtered(lambda s: not s.lab_portal_column)._lab_init_portal_columns()
        return stages
