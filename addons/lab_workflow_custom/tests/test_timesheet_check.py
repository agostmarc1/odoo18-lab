"""Consuntivazione: ore attese da orario e assenze, promemoria, chiusura del mese, task
(stima, date, ore residue) e ore dei consulenti contro la fattura."""
from datetime import date, datetime, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLabTimesheetCheck(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "Test 8 ore", "tz": "UTC", "hours_per_day": 8,
            "attendance_ids": [(0, 0, {"name": f"g{d}{p}", "dayofweek": str(d),
                                       "hour_from": hf, "hour_to": ht, "day_period": p})
                               for d in range(5)
                               for hf, ht, p in ((8, 12, "morning"), (13, 17, "afternoon"))]})
        cls.dev = new_test_user(cls.env, "t_tc_dev", groups="lab_workflow_custom.group_lab_team",
                                email="dev@test.example")
        cls.pm = new_test_user(cls.env, "t_tc_pm", groups="lab_workflow_custom.group_lab_pm")
        cls.admin_user = new_test_user(
            cls.env, "t_tc_amm", groups="lab_workflow_custom.group_lab_amministrazione")
        cls.employee = cls.env["hr.employee"].create({
            "name": "Dev Consuntivo", "user_id": cls.dev.id, "work_email": "dev@test.example",
            "resource_calendar_id": cls.calendar.id, "hourly_cost": 30, "tz": "UTC"})
        cls.project = cls.env["project.project"].create({
            "name": "Progetto consuntivo", "user_id": cls.pm.id, "allow_timesheets": True})
        cls.task = cls.env["project.task"].create({
            "name": "Sviluppo", "project_id": cls.project.id, "allocated_hours": 20})
        # un lunedì di almeno tre settimane fa: settimana intera nel passato
        today = date.today()
        cls.monday = today - timedelta(days=today.weekday() + 21)
        cls.Day = cls.env["lab.timesheet.day"]

    def _log(self, day, hours, **kw):
        return self.env["account.analytic.line"].create(dict({
            "name": "lavoro", "project_id": self.project.id, "task_id": self.task.id,
            "employee_id": self.employee.id, "date": day, "unit_amount": hours}, **kw))

    def _row(self, day):
        return self.Day.search([("employee_id", "=", self.employee.id), ("date", "=", day)])

    def test_01_expected_logged_missing(self):
        self._log(self.monday, 5)
        self.Day._lab_refresh(self.monday, self.monday + timedelta(days=6), self.employee)
        row = self._row(self.monday)
        self.assertEqual((row.due_hours, row.logged_hours, row.missing_hours), (8, 5, 3))
        self.assertEqual(row.state, "missing")
        self.assertEqual(row.week_start, self.monday)
        self.assertFalse(self._row(self.monday + timedelta(days=5)), "sabato: nessuna riga")
        # completando la giornata la riga si aggiorna da sola
        self._log(self.monday, 3)
        self.assertEqual(self._row(self.monday).state, "ok")

    def test_02_leave_and_part_time_and_excluded(self):
        # assenza: un giorno con ore da orario 8, attese 0
        self.env["resource.calendar.leaves"].create({
            "name": "Ferie", "resource_id": self.employee.resource_id.id,
            "calendar_id": self.calendar.id, "time_type": "leave",
            "date_from": datetime.combine(self.monday, datetime.min.time()),
            "date_to": datetime.combine(self.monday, datetime.max.time())})
        part_time = self.env["resource.calendar"].create({
            "name": "Part-time", "tz": "UTC", "hours_per_day": 4,
            "attendance_ids": [(0, 0, {"name": f"m{d}", "dayofweek": str(d), "hour_from": 9,
                                       "hour_to": 13, "day_period": "morning"}) for d in range(5)]})
        other = self.env["hr.employee"].create({
            "name": "Part-time", "user_id": new_test_user(self.env, "t_tc_pt").id,
            "resource_calendar_id": part_time.id, "tz": "UTC"})
        self.Day._lab_refresh(self.monday, self.monday + timedelta(days=1),
                              self.employee | other)
        row = self._row(self.monday)
        self.assertEqual((row.expected_hours, row.leave_hours, row.due_hours), (8, 8, 0))
        self.assertEqual(row.state, "absent")
        pt = self.Day.search([("employee_id", "=", other.id), ("date", "=", self.monday)])
        self.assertEqual(pt.due_hours, 4)
        # chi non deve consuntivare non compare
        other.lab_timesheet_required = False
        self.Day._lab_refresh_recent()
        self.assertFalse(self.Day.search([("employee_id", "=", other.id)]))

    def test_03_reminders_only_to_the_person(self):
        today = date.today()
        day = self.Day._lab_previous_workday(self.employee, today)
        self._log(day, 6)
        Mail = self.env["mail.mail"]
        before = Mail.search([]).ids
        self.assertGreaterEqual(self.Day._cron_daily_reminder(), 1)
        mail = Mail.search([("id", "not in", before), ("email_to", "=", "dev@test.example")])
        self.assertEqual(len(mail), 1)
        self.assertEqual(mail.email_to, "dev@test.example")
        self.assertIn("mancano 2:00 ore", mail.subject)
        # riepilogo del lunedì: settimana scorsa, alla persona
        before = Mail.search([]).ids
        self.assertGreaterEqual(self.Day._cron_weekly_summary(), 1)
        mail = Mail.search([("id", "not in", before), ("email_to", "=", "dev@test.example")])
        self.assertTrue(mail)
        self.assertIn("Le tue ore della settimana", mail.subject)

    def test_04_month_close_checks_and_locks_hours(self):
        # un mese di due anni fa: nessun dato del laboratorio
        first = date(date.today().year - 2, 3, 1)
        period = self.env["lab.cost.period"]._get_or_create(first)
        workday = first + timedelta(days=(7 - first.weekday()) % 7)  # primo lunedì del mese
        self._log(workday, 4)
        with self.assertRaises(UserError) as error:
            period.with_user(self.admin_user).action_close()
        self.assertIn("Dev Consuntivo", str(error.exception))
        period.with_user(self.admin_user).action_close_force()
        self.assertEqual(period.state, "closed")
        line = self.env["account.analytic.line"].search([
            ("employee_id", "=", self.employee.id), ("date", "=", workday)])
        # mese chiuso: la persona non aggiunge, modifica o cancella ore di quel mese
        with self.assertRaises(ValidationError):
            line.with_user(self.dev).write({"unit_amount": 8})
        with self.assertRaises(ValidationError):
            self.env["account.analytic.line"].with_user(self.dev).create({
                "name": "tardi", "project_id": self.project.id, "task_id": self.task.id,
                "employee_id": self.employee.id, "date": workday, "unit_amount": 4})
        with self.assertRaises(ValidationError):
            line.with_user(self.dev).unlink()
        # dopo una riapertura o da amministratore di sistema la correzione si può fare
        line.with_user(self.env.ref("base.user_admin")).write({"unit_amount": 8})
        self.assertEqual(line.unit_amount, 8)

    def test_05_task_estimate_dates_and_remaining(self):
        task = self.env["project.task"].create({"name": "Nuovo", "project_id": self.project.id})
        self.assertTrue(task.lab_to_estimate)
        self.assertEqual(task.lab_schedule_state, "to_estimate")
        today = date.today()
        task.write({"allocated_hours": 10,
                    "planned_date_start": datetime.combine(today - timedelta(days=5),
                                                           datetime.min.time()),
                    "planned_date_end": datetime.combine(today + timedelta(days=5),
                                                         datetime.min.time())})
        self.assertFalse(task.lab_to_estimate)
        self.assertEqual(task.lab_schedule_state, "late_start", "inizio passato, nessuna ora")
        # la persona registra 4 ore e indica che ne mancano 10: sforerà la stima
        self.env["account.analytic.line"].create({
            "name": "lavoro", "project_id": self.project.id, "task_id": task.id,
            "employee_id": self.employee.id, "date": today - timedelta(days=5),
            "unit_amount": 4, "lab_remaining_hours": 10})
        self.assertEqual(task.lab_schedule_state, "on_time")
        self.assertEqual(task.lab_date_first_work, today - timedelta(days=5))
        self.assertEqual(task.lab_remaining_estimate, 10)
        self.assertEqual(task.lab_eac_hours, 14)
        self.assertAlmostEqual(task.lab_progress_pct, 4 / 14 * 100)
        self.assertTrue(task.lab_forecast_over)
        activity = task.activity_ids.filtered(lambda a: a.summary == "Il task sforerà la stima")
        self.assertEqual(activity.user_id, self.pm, "attività al PM del progetto")
        # senza ore residue indicate: stima a finire = tempo stimato
        self.assertEqual(self.task.lab_eac_hours, 20)
        # progetto: avanzamento sulla stima a finire, task che sforeranno
        self.project.invalidate_recordset()
        self.assertEqual(self.project.lab_forecast_over_count, 1)
        self.assertEqual(self.project.lab_eac_task_hours, 34)
        # internal project tasks: niente stima richiesta
        internal = self.env.company.internal_project_id
        if internal:
            meeting = self.env["project.task"].create({"name": "Riunione",
                                                       "project_id": internal.id})
            self.assertFalse(meeting.lab_to_estimate)

    def test_06_consultant_hours_vs_bill(self):
        vendor = self.env["res.partner"].create({"name": "Consulente Srl"})
        consultant = self.env["hr.employee"].create({
            "name": "Consulente", "lab_resource_type": "external", "lab_vendor_id": vendor.id,
            "lab_external_rate": 50, "lab_external_rate_unit": "hour",
            "resource_calendar_id": self.calendar.id})
        self.project.account_id or self.project._create_analytic_account()
        for hours in (6, 4):
            self.env["account.analytic.line"].create({
                "name": "consulenza", "project_id": self.project.id, "task_id": self.task.id,
                "employee_id": consultant.id, "date": self.monday, "unit_amount": hours})
        bill = self.env["account.move"].create({
            "move_type": "in_invoice", "partner_id": vendor.id, "invoice_date": date.today(),
            "invoice_line_ids": [(0, 0, {
                "name": "Consulenza", "quantity": 12, "price_unit": 50,
                "lab_consultant_id": consultant.id,
                "analytic_distribution": {str(self.project.account_id.id): 100}})]})
        bill.action_post()
        line = bill.invoice_line_ids
        self.assertEqual(line.lab_consultant_hours, 10)
        self.assertEqual(line.lab_billed_hours, 12)
        self.assertEqual(line.lab_hours_difference, 2)
        self.assertIn("Ore del consulente non quadrano",
                      " ".join(bill.message_ids.mapped("body")))
