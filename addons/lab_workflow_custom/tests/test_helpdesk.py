from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

RAW_EMAIL = """From: Mario Verdi <{email}>
To: assistenza@example.com
Subject: {subject}
Message-ID: <{msgid}@lab.example>
Content-Type: text/plain; charset="utf-8"

La stampa dei DDT si blocca con un errore.
"""


@tagged("post_install", "-at_install")
class TestLabHelpdesk(TransactionCase):
    """Ticketing: ticket -> contatto -> commessa AMS -> ore sul monte ore -> SLA -> permessi."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True,
                                       mail_notrack=True))
        cls.sales = new_test_user(cls.env, "t_hd_sales",
                                  groups="lab_workflow_custom.group_lab_commerciale")
        cls.support = new_test_user(cls.env, "t_hd_support",
                                    groups="lab_workflow_custom.group_lab_support")
        cls.support_employee = cls.env["hr.employee"].create(
            {"name": "Supporto Test", "user_id": cls.support.id, "hourly_cost": 30})
        cls.customer = cls.env["res.partner"].create({
            "name": "Cliente AMS Srl", "is_company": True, "email": "it@cliente-ams.example",
            "user_id": cls.sales.id})
        cls.contact = cls.env["res.partner"].create({
            "name": "Mario Verdi", "parent_id": cls.customer.id,
            "email": "mario.verdi@cliente-ams.example"})
        cls.ams_project = cls._confirmed_project(
            cls.customer, "lab_workflow_custom.product_ams_monthly")
        cls.team = cls.env.ref("lab_workflow_custom.helpdesk_team_support")
        cls.team.user_ids = [(4, cls.support.id)]

    @classmethod
    def _confirmed_project(cls, partner, product_xmlid):
        order = cls.env["sale.order"].with_user(cls.sales).create({
            "partner_id": partner.id,
            "order_line": [(0, 0, {"product_id": cls.env.ref(product_xmlid).product_variant_id.id,
                                   "product_uom_qty": 1})]})
        order.with_user(cls.sales).action_confirm()
        line = order.sudo().order_line
        return line.task_id.project_id or line.project_id

    def _ticket(self, **vals):
        return self.env["helpdesk.ticket"].create(dict(
            {"name": "Problema", "description": "<p>Descrizione</p>"}, **vals))

    def test_01_configuration(self):
        self.assertTrue(self.team.allow_timesheet)
        self.assertTrue(self.team.use_sla)
        self.assertEqual(self.team.alias_name, "assistenza")
        self.assertEqual(len(self.team.type_ids), 3)
        done = self.env.ref("helpdesk_mgmt.helpdesk_ticket_stage_done")
        self.assertEqual(done.mail_template_id,
                         self.env.ref("lab_workflow_custom.mail_template_ticket_done"))
        self.assertTrue(done.rating_mail_template_id, "Alla chiusura parte la valutazione")
        page = self.env["website.page"].search([("url", "=", "/assistenza")])
        self.assertTrue(page.is_published)

    def test_02_email_creates_ticket_on_ams_project(self):
        raw = RAW_EMAIL.format(email=self.contact.email, subject="Stampa DDT bloccata",
                               msgid="t02")
        ticket_id = self.env["mail.thread"].message_process("helpdesk.ticket", raw)
        ticket = self.env["helpdesk.ticket"].browse(ticket_id)
        self.assertEqual(ticket.name, "Stampa DDT bloccata")
        self.assertEqual(ticket.partner_id, self.contact)
        self.assertEqual(ticket.project_id, self.ams_project,
                         "Il ticket del cliente a canone va da solo sulla commessa AMS")
        self.assertEqual(ticket.team_id, self.team)
        self.assertFalse(ticket.user_id, "Da assegnare: non all'utente tecnico che legge la posta")
        self.assertEqual(ticket.lab_contract_type, "canone")
        self.assertIn(self.contact, ticket.message_partner_ids,
                      "Il cliente segue il ticket e riceve le risposte per email")
        self.assertIn(self.env.ref("lab_workflow_custom.helpdesk_sla_ams_resolution"),
                      ticket.sla_ids)
        self.assertTrue(ticket.sla_deadline)

    def test_03_web_ticket_waits_for_email_confirmation(self):
        """Dal sito: il ticket aspetta la conferma via email prima di collegarsi all'azienda."""
        Ticket = self.env["helpdesk.ticket"].with_user(self.env.ref("base.user_root")).sudo()
        ticket = Ticket.with_context(lab_from_website=True).create({
            "name": "Dal sito", "description": "<p>x</p>", "partner_name": "Mario",
            "partner_email": "Mario.Verdi@Cliente-AMS.example"})
        self.assertFalse(ticket.lab_web_confirmed)
        self.assertFalse(ticket.partner_id, "Chiunque può scrivere un'email altrui: niente azienda")
        self.assertFalse(ticket.project_id, "...e niente ore sul monte ore del cliente")
        self.assertFalse(ticket.sla_ids, "Gli SLA partono dalla conferma")
        self.assertFalse(ticket.user_id, "Il ticket dal sito non va assegnato a OdooBot")
        self.assertEqual(ticket.channel_id,
                         self.env.ref("helpdesk_mgmt.helpdesk_ticket_channel_web"))
        mails = self.env["mail.mail"].search([("model", "=", "helpdesk.ticket"),
                                              ("res_id", "=", ticket.id)])
        self.assertEqual(len(mails), 1, "Solo l'email di conferma, non quella di ticket ricevuto")
        self.assertIn("Conferma la tua richiesta", mails.subject)
        self.assertIn(f"/assistenza/conferma/{ticket.id}/{ticket.lab_confirm_token}",
                      mails.body_html)
        self.assertEqual(mails.email_to, "Mario.Verdi@Cliente-AMS.example")
        # codice sbagliato: nulla
        Model = self.env["helpdesk.ticket"]
        self.assertFalse(Model._lab_check_confirm_token(ticket.id, "codice-inventato"))
        self.assertFalse(Model._lab_check_confirm_token(ticket.id, ""))
        # codice giusto: conferma
        token = ticket.lab_confirm_token
        found = Model._lab_check_confirm_token(ticket.id, token)
        self.assertEqual(found, ticket)
        found._lab_web_confirm()
        self.assertTrue(ticket.lab_web_confirmed)
        self.assertEqual(ticket.partner_id, self.contact, "Email riconosciuta anche in maiuscolo")
        self.assertEqual(ticket.project_id, self.ams_project)
        self.assertIn(self.env.ref("lab_workflow_custom.helpdesk_sla_ams_resolution"),
                      ticket.sla_ids)
        self.assertIn(self.contact, ticket.message_partner_ids)
        received = self.env["mail.mail"].search([("model", "=", "helpdesk.ticket"),
                                                 ("res_id", "=", ticket.id)]) - mails
        self.assertIn("Abbiamo ricevuto", received.subject)
        self.assertFalse(Model._lab_check_confirm_token(ticket.id, token), "Link usa e getta")

    def test_04_unknown_email_stays_unlinked(self):
        ticket = self._ticket(partner_name="Sconosciuto", partner_email="nuovo@altro.example")
        self.assertFalse(ticket.partner_id)
        self.assertFalse(ticket.project_id)
        self.assertEqual(ticket.partner_email, "nuovo@altro.example")
        self.assertIn(self.env.ref("lab_workflow_custom.helpdesk_sla_standard"), ticket.sla_ids)

    def test_05_hours_on_ticket_consume_ams_hours_and_alert(self):
        ticket = self._ticket(partner_id=self.contact.id)
        self.env["account.analytic.line"].create({
            "name": "Analisi errore", "ticket_id": ticket.id,
            "employee_id": self.support_employee.id, "unit_amount": 16})
        self.assertEqual(ticket.total_hours, 16)
        self.assertEqual(ticket.timesheet_ids.project_id, self.ams_project,
                         "Le ore sul ticket vanno sulla commessa del ticket")
        self.ams_project.invalidate_recordset()
        self.assertEqual(self.ams_project.lab_consumed_hours, 16)
        self.assertEqual(self.ams_project.lab_alert_level, "warning", "16h su 20 = 80%")
        ticket.invalidate_recordset()
        self.assertEqual(ticket.lab_hours_alert, "warning")

    def test_06_hours_package_ticket_needs_task(self):
        package = self._confirmed_project(self.customer, "lab_workflow_custom.product_hours_pack_50")
        ticket = self._ticket(partner_id=self.contact.id, project_id=package.id)
        with self.assertRaises(ValidationError):
            self.env["account.analytic.line"].create({
                "name": "x", "ticket_id": ticket.id, "employee_id": self.support_employee.id,
                "unit_amount": 1})
        task = package.task_ids[:1]
        ticket.task_id = task
        line = self.env["account.analytic.line"].create({
            "name": "x", "ticket_id": ticket.id, "employee_id": self.support_employee.id,
            "unit_amount": 1})
        self.assertEqual(line.task_id, task, "Il task arriva dal ticket")

    def test_07_urgent_sla_and_priority_change(self):
        ticket = self._ticket(partner_id=self.contact.id, priority="1")
        urgent = self.env.ref("lab_workflow_custom.helpdesk_sla_ams_urgent")
        normal = self.env.ref("lab_workflow_custom.helpdesk_sla_ams_normal")
        self.assertIn(normal, ticket.sla_ids)
        self.assertNotIn(urgent, ticket.sla_ids)
        ticket.priority = "3"
        self.assertIn(urgent, ticket.sla_ids, "Diventato urgente: SLA 4 ore")
        self.assertNotIn(normal, ticket.sla_ids)

    def test_08_website_rate_limit(self):
        Ticket = self.env["helpdesk.ticket"]
        with self.assertRaises(UserError):
            Ticket._lab_check_website_rate("non-una-email")
        self.env["ir.config_parameter"].sudo().set_param(
            "lab_workflow_custom.helpdesk_web_max_per_hour", 2)
        for i in range(2):
            Ticket._lab_check_website_rate("spam@bot.example")
            Ticket.with_context(lab_from_website=True).create({
                "name": f"Spam {i}", "description": "<p>x</p>",
                "partner_email": "spam@bot.example"})
        with self.assertRaises(UserError):
            Ticket._lab_check_website_rate("spam@bot.example")
        Ticket._lab_check_website_rate("altro@cliente.example")  # gli altri non sono bloccati

    def test_09_roles(self):
        ticket = self._ticket(partner_id=self.contact.id)
        other = self.env["res.partner"].create({"name": "Altro cliente", "email": "a@b.example"})
        foreign = self._ticket(partner_id=other.id)
        # Supporto: tutti i ticket, li prende in carico
        self.assertEqual(ticket.with_user(self.support).read(["name"])[0]["name"], "Problema")
        ticket.with_user(self.support).assign_to_me()
        self.assertEqual(ticket.user_id, self.support)
        # Commerciale: legge i ticket dei suoi clienti, non li modifica, non vede gli altri
        Ticket = self.env["helpdesk.ticket"].with_user(self.sales)
        self.assertIn(ticket, Ticket.search([]))
        self.assertNotIn(foreign, Ticket.search([]))
        with self.assertRaises(AccessError):
            ticket.with_user(self.sales).write({"name": "Modificato"})

    def test_10_web_description_rich_text_and_images(self):
        """Descrizione dall'editor del sito: formattazione e link restano, codice pericoloso no,
        le immagini incollate diventano allegati del ticket."""
        png = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAA"
               "AABJRU5ErkJggg==")
        raw = ('<p>La stampa <b>si blocca</b>, vedi <a href="https://www.esempio.it">guida</a>'
               ' <a href="javascript:alert(1)">trappola</a></p>'
               '<ul><li>apro i DDT</li><li>premo Stampa</li></ul>'
               f'<p><img src="data:image/png;base64,{png}"></p>'
               '<img src="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=">'
               '<img src="data:image/png;base64,bm9uIHVuJ2ltbWFnaW5l">'
               '<script>alert(2)</script>')
        Ticket = self.env["helpdesk.ticket"].with_context(lab_rich_description=True)
        fake_request = type("FakeRequest", (), {"params": {"description": raw}})()
        values = Ticket.website_form_input_filter(fake_request, {"description": "<p>testo</p>"})
        self.assertIn("<b>si blocca</b>", values["description"])
        self.assertIn('href="https://www.esempio.it"', values["description"])
        self.assertNotIn("javascript", values["description"])
        self.assertNotIn("<script", values["description"])
        ticket = Ticket.with_context(lab_from_website=True).create({
            "name": "Con immagini", "partner_email": "x@cliente.example", **values})
        self.assertIn("<li>premo Stampa</li>", ticket.description)
        self.assertNotIn("data:", ticket.description, "Niente immagini incorporate nel testo")
        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", "helpdesk.ticket"), ("res_id", "=", ticket.id)])
        self.assertEqual(len(attachments), 1, "Solo l'immagine PNG vera; SVG e falsi scartati")
        self.assertEqual(attachments.mimetype, "image/png")
        self.assertIn(f"/web/image/{attachments.id}?access_token={attachments.access_token}",
                      ticket.description)
        # senza editor (JavaScript spento) la descrizione resta quella del form builder
        plain = self.env["helpdesk.ticket"].website_form_input_filter(
            fake_request, {"description": "<p>testo</p>"})
        self.assertEqual(plain["description"], "<p>testo</p>")

    def test_11_confirmation_trusted_manual_and_cleanup(self):
        Ticket = self.env["helpdesk.ticket"].with_context(lab_from_website=True)
        # utente collegato che usa la propria email: niente conferma
        trusted = Ticket.with_context(lab_web_trusted=True).create({
            "name": "Dal portale", "description": "<p>x</p>",
            "partner_email": self.contact.email})
        self.assertTrue(trusted.lab_web_confirmed)
        self.assertEqual(trusted.project_id, self.ams_project)
        # conferma a mano del Supporto (il cliente ha telefonato); il Commerciale non può
        pending = Ticket.create({"name": "Telefonata", "description": "<p>x</p>",
                                 "partner_email": self.contact.email})
        with self.assertRaises(UserError):
            pending.with_user(self.sales).action_lab_web_confirm()
        pending.with_user(self.support).action_lab_web_confirm()
        self.assertTrue(pending.lab_web_confirmed)
        self.assertEqual(pending.partner_id, self.contact)
        # mai confermati da oltre 7 giorni: archiviati dalla pulizia notturna
        stale = Ticket.create({"name": "Spam", "description": "<p>x</p>",
                               "partner_email": "spam@bot.example"})
        recent = Ticket.create({"name": "Recente", "description": "<p>x</p>",
                                "partner_email": "nuovo@bot.example"})
        self.env.cr.execute("UPDATE helpdesk_ticket SET create_date = now() - interval '8 days' "
                            "WHERE id = %s", [stale.id])
        stale.invalidate_recordset()
        self.env["helpdesk.ticket"]._lab_archive_unconfirmed()
        self.assertFalse(stale.active)
        self.assertTrue(recent.active)
        self.assertFalse(self.env["helpdesk.ticket"]._lab_check_confirm_token(
            stale.id, stale.lab_confirm_token or "x"), "Il link di un ticket archiviato non vale")

    def _portal_user(self, login, company):
        user = new_test_user(self.env, login, groups="base.group_portal")
        user.partner_id.write({"parent_id": company.id, "email": f"{login}@x.example"})
        return user

    def test_12_portal_segregation_by_company(self):
        """Ogni cliente vede solo i ticket della propria azienda, anche se è follower di altri."""
        other_company = self.env["res.partner"].create({"name": "Altra Srl", "is_company": True})
        mine = self._ticket(partner_id=self.contact.id)
        foreign = self._ticket(partner_id=other_company.id)
        verdi = self._portal_user("t_portal_ams", self.customer)
        altra = self._portal_user("t_portal_altra", other_company)
        # errore del Supporto: il cliente AMS aggiunto come follower al ticket dell'altra azienda
        foreign.message_subscribe(partner_ids=verdi.partner_id.ids)
        seen = self.env["helpdesk.ticket"].with_user(verdi).search([])
        self.assertIn(mine, seen)
        self.assertNotIn(foreign, seen, "Il follower di un'altra azienda non vede il ticket")
        with self.assertRaises(AccessError):
            foreign.with_user(verdi).read(["name"])
        self.assertEqual(self.env["helpdesk.ticket"].with_user(altra).search([]), foreign)
        # gli utenti interni non sono toccati dalla regola
        self.assertIn(foreign, self.env["helpdesk.ticket"].with_user(self.support).search([]))

    def test_13_portal_realtime_notification_only_to_own_company(self):
        from unittest.mock import patch
        other_company = self.env["res.partner"].create({"name": "Altra Srl", "is_company": True})
        verdi = self._portal_user("t_portal_ams2", self.customer)
        altra = self._portal_user("t_portal_altra2", other_company)
        ticket = self._ticket(partner_id=self.contact.id)
        sent = []
        Partner = type(self.env["res.partner"])

        def fake_send(partners, notification_type, message, *args, **kwargs):
            sent.extend((p, notification_type, message) for p in partners)

        with patch.object(Partner, "_bus_send", fake_send):
            ticket.stage_id = self.env.ref("helpdesk_mgmt.helpdesk_ticket_stage_in_progress")
        self.assertEqual([(p, t) for p, t, _m in sent], [(verdi.partner_id, "lab_ticket_update")])
        self.assertEqual(sent[0][2], {"ticket_ids": [ticket.id]})
        self.assertNotIn(altra.partner_id, [p for p, _t, _m in sent])


@tagged("post_install", "-at_install")
class TestLabPortalKanban(HttpCase):
    """La pagina Kanban del portale, vista da un cliente collegato."""

    def test_portal_kanban_page(self):
        env = self.env(context=dict(self.env.context, tracking_disable=True))
        company = env["res.partner"].create({"name": "Cliente Kanban Srl", "is_company": True})
        other = env["res.partner"].create({"name": "Concorrente Srl", "is_company": True})
        user = new_test_user(env, "t_portal_kanban", groups="base.group_portal")
        user.partner_id.write({"parent_id": company.id, "email": "kanban@cliente.example"})
        Ticket = env["helpdesk.ticket"]
        mine = Ticket.create({"name": "Ticket del cliente", "description": "<p>x</p>",
                              "partner_id": company.id})
        foreign = Ticket.create({"name": "Ticket del concorrente", "description": "<p>x</p>",
                                 "partner_id": other.id})
        self.authenticate("t_portal_kanban", "t_portal_kanban")
        page = self.url_open("/my/tickets/kanban")
        self.assertEqual(page.status_code, 200)
        self.assertIn(mine.number, page.text)
        self.assertIn("Ticket del cliente", page.text)
        self.assertNotIn(foreign.number, page.text)
        self.assertNotIn("Ticket del concorrente", page.text)
        self.assertIn('id="lab_ticket_kanban"', page.text)
        fragment = self.url_open("/my/tickets/kanban?fragment=1&scope=mine")
        self.assertIn("lab_kanban_board", fragment.text)
        self.assertNotIn(mine.number, fragment.text, "Solo i miei: il ticket è dell'azienda")
