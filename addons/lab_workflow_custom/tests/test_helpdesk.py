from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

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

    def test_03_web_email_matches_contact(self):
        # come il form del sito: creazione con il superutente
        Ticket = self.env["helpdesk.ticket"].with_user(self.env.ref("base.user_root")).sudo()
        ticket = Ticket.with_context(lab_from_website=True).create({
            "name": "Dal sito", "description": "<p>x</p>", "partner_name": "Mario",
            "partner_email": "Mario.Verdi@Cliente-AMS.example"})
        self.assertEqual(ticket.partner_id, self.contact, "Email riconosciuta anche in maiuscolo")
        self.assertFalse(ticket.user_id, "Il ticket dal sito non va assegnato a OdooBot")
        self.assertEqual(ticket.project_id, self.ams_project)
        self.assertEqual(ticket.channel_id,
                         self.env.ref("helpdesk_mgmt.helpdesk_ticket_channel_web"))

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
