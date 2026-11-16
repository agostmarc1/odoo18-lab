"""Controllo della consuntivazione: una riga per persona e giorno lavorativo.

Ore attese = orario di lavoro della persona (scheda dipendente, campo standard "Orario di
lavoro") meno assenze approvate (Ferie e permessi) e festività. Ore registrate = fogli ore del
giorno (progetti dei clienti e progetto interno). Mancanti = attese - registrate (mai negative).

Le righe sono un registro calcolato: le aggiorna il sistema quando cambiano fogli ore o assenze,
ogni notte e all'apertura del report. Promemoria per email solo alla persona interessata:
ogni mattina per il giorno lavorativo precedente, il lunedì il riepilogo della settimana prima.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import api, fields, models

TOLERANCE = 0.01  # ore: sotto questa soglia la differenza non conta
REFRESH_DAYS = 62  # giorni ricalcolati ogni notte e all'apertura del report


class LabTimesheetDay(models.Model):
    _name = "lab.timesheet.day"
    _description = "Consuntivazione giornaliera"
    _order = "date desc, employee_id"
    _rec_name = "employee_id"

    employee_id = fields.Many2one("hr.employee", "Persona", required=True, index=True,
                                  ondelete="cascade")
    user_id = fields.Many2one("res.users", "Utente", index=True)
    department_id = fields.Many2one("hr.department", "Reparto")
    is_external = fields.Boolean("Consulente esterno")
    date = fields.Date("Giorno", required=True, index=True)
    week_start = fields.Date("Settimana (lunedì)", index=True)
    month_start = fields.Date("Mese", index=True)
    expected_hours = fields.Float("Ore da orario", aggregator="sum")
    leave_hours = fields.Float("Assenze e festività", aggregator="sum")
    due_hours = fields.Float("Ore attese", aggregator="sum",
                             help="Ore da orario meno assenze e festività.")
    logged_hours = fields.Float("Ore registrate", aggregator="sum")
    missing_hours = fields.Float("Ore mancanti", aggregator="sum")
    extra_hours = fields.Float("Ore in più", aggregator="sum")
    state = fields.Selection([
        ("ok", "Completo"),
        ("missing", "Ore mancanti"),
        ("absent", "Assente"),
    ], "Stato", index=True)
    company_id = fields.Many2one("res.company", required=True)

    _sql_constraints = [("employee_day_unique", "unique(employee_id, date)",
                         "Una sola riga per persona e giorno.")]

    # ---- Calcolo ------------------------------------------------------------
    @api.model
    def _lab_employees(self):
        """Chi deve consuntivare: persone attive con utente e orario di lavoro."""
        return self.env["hr.employee"].sudo().search([
            ("user_id", "!=", False), ("resource_calendar_id", "!=", False),
            ("lab_timesheet_required", "=", True)])

    @api.model
    def _lab_refresh(self, date_from, date_to, employees=None):
        """Ricalcola le righe del periodo, fino a ieri: la giornata di oggi è ancora in corso."""
        date_to = min(date_to, fields.Date.context_today(self) - timedelta(days=1))
        if date_from > date_to:
            return
        employees = (employees or self._lab_employees()).sudo().filtered(
            lambda e: e.user_id and e.resource_calendar_id and e.lab_timesheet_required)
        if not employees:
            return
        start = datetime.combine(date_from, time.min)
        stop = datetime.combine(date_to + timedelta(days=1), time.min)
        gross = employees.with_context(compute_leaves=False)._list_work_time_per_day(start, stop)
        net = employees._list_work_time_per_day(start, stop)
        logged = defaultdict(float)
        AAL = self.env["account.analytic.line"].sudo()
        domain = [("employee_id", "in", employees.ids), ("project_id", "!=", False),
                  ("date", ">=", date_from), ("date", "<=", date_to)]
        # ore create da Odoo per ferie e festività (task "Time Off"): sono assenze, non lavoro
        for field in ("holiday_id", "global_leave_id"):
            if field in AAL._fields:
                domain.append((field, "=", False))
        for employee, day, hours in AAL._read_group(
                domain,
                ["employee_id", "date:day"], ["unit_amount:sum"]):
            logged[(employee.id, fields.Date.to_date(day))] += hours
        Day = self.sudo()
        existing = {(d.employee_id.id, d.date): d for d in Day.search([
            ("employee_id", "in", employees.ids), ("date", ">=", date_from),
            ("date", "<=", date_to)])}
        to_create, seen = [], set()
        for employee in employees:
            gross_days = {d: h for d, h in gross.get(employee.id, [])}
            net_days = {d: h for d, h in net.get(employee.id, [])}
            days = set(gross_days) | {d for (e, d) in logged if e == employee.id}
            for day in days:
                expected = gross_days.get(day, 0.0)
                due = net_days.get(day, 0.0)
                done = logged.get((employee.id, day), 0.0)
                missing = max(due - done, 0.0)
                state = ("absent" if expected and due < TOLERANCE and done < TOLERANCE
                         else "missing" if missing > TOLERANCE else "ok")
                vals = {
                    "employee_id": employee.id, "user_id": employee.user_id.id,
                    "department_id": employee.department_id.id,
                    "is_external": employee.lab_resource_type == "external",
                    "date": day, "week_start": day - timedelta(days=day.weekday()),
                    "month_start": day.replace(day=1),
                    "expected_hours": expected, "leave_hours": max(expected - due, 0.0),
                    "due_hours": due, "logged_hours": done, "missing_hours": missing,
                    "extra_hours": max(done - due, 0.0), "state": state,
                    "company_id": employee.company_id.id,
                }
                seen.add((employee.id, day))
                row = existing.get((employee.id, day))
                if row:
                    changed = {k: v for k, v in vals.items()
                               if (row[k].id if isinstance(row[k], models.BaseModel) else row[k]) != v}
                    if changed:
                        row.write(changed)
                else:
                    to_create.append(vals)
        if to_create:
            Day.create(to_create)
        # giorni non più lavorativi e senza ore (es. orario cambiato): via
        Day.browse([r.id for key, r in existing.items() if key not in seen]).unlink()

    @api.model
    def _lab_refresh_recent(self):
        today = fields.Date.context_today(self)
        # via le righe di oggi (giornata in corso) e di chi non deve più consuntivare
        self.sudo().search(["|", ("date", ">=", today),
                            ("employee_id.lab_timesheet_required", "=", False)]).unlink()
        self._lab_refresh(today - timedelta(days=REFRESH_DAYS), today)

    # ---- Promemoria (solo alla persona) -------------------------------------
    @api.model
    def _lab_previous_workday(self, employee, today):
        """Ultimo giorno lavorativo prima di oggi per l'orario della persona (max 7 giorni)."""
        start = datetime.combine(today - timedelta(days=7), time.min)
        stop = datetime.combine(today, time.min)
        days = [d for d, h in employee.with_context(compute_leaves=False)
                ._list_work_time_per_day(start, stop).get(employee.id, []) if h]
        return max(days) if days else None

    @api.model
    def _cron_daily_reminder(self):
        """Ogni mattina: chi ieri (ultimo giorno lavorativo) ha ore mancanti riceve un'email."""
        today = fields.Date.context_today(self)
        template = self.env.ref("lab_workflow_custom.mail_template_timesheet_daily")
        sent = 0
        for employee in self._lab_employees():
            day = self._lab_previous_workday(employee, today)
            if not day:
                continue
            self._lab_refresh(day, day, employee)
            row = self.sudo().search([("employee_id", "=", employee.id), ("date", "=", day)])
            if row.state == "missing" and employee.work_email:
                template.sudo().send_mail(row.id, email_layout_xmlid="mail.mail_notification_light")
                sent += 1
        return sent

    @api.model
    def _cron_weekly_summary(self):
        """Il lunedì: a ognuno il riepilogo della settimana prima (solo se ha ore attese)."""
        today = fields.Date.context_today(self)
        monday = today - timedelta(days=today.weekday() + 7)
        sunday = monday + timedelta(days=6)
        self._lab_refresh(monday, sunday)
        template = self.env.ref("lab_workflow_custom.mail_template_timesheet_weekly")
        sent = 0
        for employee in self._lab_employees():
            rows = self.sudo().search([("employee_id", "=", employee.id),
                                       ("date", ">=", monday), ("date", "<=", sunday)])
            if not rows or not employee.work_email:
                continue
            template.sudo().with_context(lab_week_row_ids=rows.ids).send_mail(
                rows.sorted("date")[0].id, email_layout_xmlid="mail.mail_notification_light")
            sent += 1
        return sent

    def _lab_week_rows(self):
        """Righe della settimana per il template del riepilogo (passate dal contesto)."""
        ids = self.env.context.get("lab_week_row_ids")
        return self.browse(ids) if ids else self

    @api.model
    def _lab_format_hours(self, hours):
        minutes = round((hours or 0.0) * 60)
        return "%d:%02d" % divmod(minutes, 60)

    # ---- Mese: controllo prima della chiusura -------------------------------
    @api.model
    def _lab_missing_by_employee(self, date_from, date_to):
        """{persona: ore mancanti} del periodo (dopo averlo ricalcolato)."""
        self._lab_refresh(date_from, date_to)
        result = defaultdict(float)
        for row in self.sudo().search([("date", ">=", date_from), ("date", "<=", date_to),
                                       ("state", "=", "missing")]):
            result[row.employee_id] += row.missing_hours
        return dict(result)

    @api.model
    def _lab_refresh_for_lines(self, lines):
        """Fogli ore cambiati: ricalcola solo i giorni toccati (passati o di oggi)."""
        keys = defaultdict(set)
        for line in lines.sudo():
            if line.employee_id and line.date:
                keys[line.employee_id].add(line.date)
        for employee, days in keys.items():
            self._lab_refresh(min(days), max(days), employee)



class HrLeave(models.Model):
    """Assenza approvata, rifiutata o annullata: ricalcola i giorni interessati."""
    _inherit = "hr.leave"

    def write(self, vals):
        before = self._lab_leave_ranges()
        res = super().write(vals)
        if {"state", "request_date_from", "request_date_to", "date_from", "date_to",
                "employee_id"} & set(vals):
            self._lab_refresh_leave_days(before | self._lab_leave_ranges())
        return res

    def _lab_leave_ranges(self):
        return {(leave.employee_id.id, leave.date_from.date(), leave.date_to.date())
                for leave in self.sudo() if leave.employee_id and leave.date_from and leave.date_to}

    def _lab_refresh_leave_days(self, ranges):
        Day = self.env["lab.timesheet.day"].sudo()
        for employee_id, day_from, day_to in ranges:
            Day._lab_refresh(day_from, day_to, self.env["hr.employee"].browse(employee_id))


class HrEmployee(models.Model):
    """Orario di lavoro cambiato o "Deve consuntivare" tolto: si ricalcolano gli ultimi due mesi."""
    _inherit = "hr.employee"

    def write(self, vals):
        res = super().write(vals)
        if {"resource_calendar_id", "lab_timesheet_required", "user_id"} & set(vals):
            Day = self.env["lab.timesheet.day"].sudo()
            Day.search([("employee_id", "in", self.ids)]).filtered(
                lambda d: not d.employee_id.lab_timesheet_required).unlink()
            today = fields.Date.context_today(self)
            Day._lab_refresh(today - timedelta(days=REFRESH_DAYS), today, self)
        return res
