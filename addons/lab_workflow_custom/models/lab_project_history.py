"""Cronologia del progetto nel chatter: tutto quello che succede alla commessa, in ordine.

Il PM apre il progetto e nel chatter trova, senza cercare altrove:
- ordini di vendita confermati, fatture clienti emesse, fatture fornitori registrate;
- ticket di assistenza aperti e chiusi;
- SAL / aggiornamenti di stato (Dashboard del progetto) e incontri del Calendario;
- (già di Odoo) attività fatte (Chiamata, Incontro, SAL) con il loro esito, cambi di
  responsabile, cliente, date e fase; (già del modulo) avvisi sul monte ore.

Le note sono interne (non vanno via email al cliente) e si scrivono con i permessi di sistema,
perché chi conferma un ordine o una fattura non sempre può scrivere sul progetto.
"""
from markupsafe import Markup

from odoo import api, models
from odoo.tools import format_amount, format_datetime


def _link(record, label=None):
    return Markup('<a href="#" data-oe-model="%s" data-oe-id="%s">%s</a>') % (
        record._name, record.id, label or record.display_name)


def log_on_projects(projects, body):
    """Nota interna sul chatter dei progetti (una sola volta per progetto)."""
    # chi scrive la nota non diventa follower: le commesse riservate restano riservate
    for project in projects.sudo().with_context(mail_create_nosubscribe=True).exists():
        project.message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_note")


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _lab_projects(self):
        self.ensure_one()
        lines = self.sudo().order_line
        return (self.sudo().project_ids | self.sudo().project_id
                | lines.project_id | lines.task_id.project_id)

    def _lab_project_name(self, line=None):
        """Nome breve della commessa: riferimento del cliente, altrimenti Cliente – Prodotto."""
        self.ensure_one()
        if self.client_order_ref:
            return self.client_order_ref
        product = (line or self.order_line.filtered("is_service")[:1]).product_id
        partner = self.partner_id.commercial_partner_id.name
        return "%s – %s" % (partner, product.name) if product else partner

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            body = Markup("🧾 <b>Ordine di vendita confermato</b>: %s – %s, imponibile %s") % (
                _link(order, order.name), order.partner_id.display_name,
                format_amount(self.env, order.amount_untaxed, order.currency_id))
            log_on_projects(order._lab_projects(), body)
        return res


class AccountMove(models.Model):
    _inherit = "account.move"

    def _lab_project_amounts(self):
        """{progetto: imponibile delle righe che lo riguardano} per questa fattura."""
        self.ensure_one()
        amounts = {}
        for line in self.sudo().invoice_line_ids.filtered(lambda l: l.display_type == "product"):
            sols = line.sale_line_ids
            projects = (sols.project_id | sols.task_id.project_id | sols.order_id.project_id
                        | line._lab_projects())
            for project in projects:
                amounts[project] = amounts.get(project, 0.0) + line.price_subtotal
        return amounts

    def action_post(self):
        res = super().action_post()
        labels = {"out_invoice": ("📤", "Fattura cliente emessa"),
                  "out_refund": ("↩️", "Nota di credito cliente emessa"),
                  "in_invoice": ("📥", "Fattura fornitore registrata"),
                  "in_refund": ("↩️", "Nota di credito fornitore registrata")}
        for move in self.filtered(lambda m: m.move_type in labels and m.state == "posted"):
            icon, label = labels[move.move_type]
            for project, amount in move._lab_project_amounts().items():
                body = Markup("%s <b>%s</b>: %s – %s, imponibile su questa commessa %s") % (
                    icon, label, _link(move, move.name), move.partner_id.display_name,
                    format_amount(self.env, amount, move.currency_id))
                log_on_projects(project, body)
        return res


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def _lab_log_opened(self):
        for ticket in self.filtered("project_id"):
            body = Markup("🎫 <b>Ticket aperto</b>: %s %s (%s)") % (
                _link(ticket, ticket.number), ticket.name,
                ticket.partner_id.display_name or ticket.partner_email or "")
            log_on_projects(ticket.project_id, body)

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        tickets._lab_log_opened()
        return tickets

    def write(self, vals):
        before = {t.id: (t.project_id, t.stage_id.closed) for t in self} if (
            "project_id" in vals or "stage_id" in vals) else {}
        res = super().write(vals)
        for ticket in self.filtered(lambda t: t.id in before):
            old_project, was_closed = before[ticket.id]
            if ticket.project_id and ticket.project_id != old_project:
                ticket._lab_log_opened()
            if "stage_id" in vals and ticket.stage_id.closed and not was_closed:
                body = Markup("✅ <b>Ticket chiuso</b> (%s): %s %s") % (
                    ticket.stage_id.name, _link(ticket, ticket.number), ticket.name)
                log_on_projects(ticket.project_id, body)
        return res


class ProjectUpdate(models.Model):
    _inherit = "project.update"

    @api.model_create_multi
    def create(self, vals_list):
        updates = super().create(vals_list)
        status = dict(self._fields["status"]._description_selection(self.env))
        for update in updates:
            body = Markup("📌 <b>SAL / aggiornamento di stato</b>: %s – stato <b>%s</b>, "
                          "avanzamento %s%%") % (
                _link(update, update.name), status.get(update.status, update.status or ""),
                update.progress)
            if update.description:
                body += Markup("<br/>") + update.description
            log_on_projects(update.project_id, body)
        return updates


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        for event in events.filtered(lambda e: e.res_model == "project.project" and e.res_id):
            when = format_datetime(self.env, event.start, dt_format="short") if event.start else ""
            people = ", ".join(event.partner_ids.mapped("name"))
            body = Markup("📅 <b>Incontro pianificato</b>: %s – %s") % (_link(event, event.name), when)
            if people:
                body += Markup("<br/>Partecipanti: %s") % people
            log_on_projects(self.env["project.project"].browse(event.res_id), body)
        return events

