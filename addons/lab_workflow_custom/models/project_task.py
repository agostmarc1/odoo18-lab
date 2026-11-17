from odoo import api, fields, models

SCHEDULE_STATES = [
    ("to_estimate", "Da stimare"),
    ("not_started", "Da iniziare"),
    ("late_start", "Inizio in ritardo"),
    ("on_time", "In linea"),
    ("late_end", "Oltre la data di fine"),
    ("done", "Concluso"),
]

ALERT_LEVELS = [
    ("none", "Nessun riferimento"),
    ("ok", "Sotto il 75%"),
    ("warning", "Oltre il 75%"),
    ("danger", "Oltre il 90%"),
]


def _alert_level(consumed, reference):
    if not reference:
        return 0.0, "none"
    pct = consumed / reference * 100.0
    if pct >= 90:
        return pct, "danger"
    if pct >= 75:
        return pct, "warning"
    return pct, "ok"


class ProjectTask(models.Model):
    _inherit = "project.task"

    lab_sold_hours = fields.Float(
        "Ore vendute (riga ordine)", related="sale_line_id.lab_sold_hours")
    lab_consumption_pct = fields.Float(
        "% consumo ore", compute="_compute_lab_alert", store=True, aggregator="avg",
        help="Ore consuntivate / Ore stimate (se mancano: ore vendute della riga).")
    lab_alert_level = fields.Selection(
        ALERT_LEVELS, "Alert monte ore", compute="_compute_lab_alert", store=True)

    @api.depends("effective_hours", "allocated_hours", "sale_line_id.lab_sold_hours")
    def _compute_lab_alert(self):
        for task in self:
            reference = task.allocated_hours or task.sale_line_id.lab_sold_hours
            task.lab_consumption_pct, task.lab_alert_level = _alert_level(
                task.effective_hours, reference)

    # ---- Consuntivazione del task: stima, pianificazione, esecuzione ----------
    # Inizio e fine pianificati: planned_date_start / planned_date_end (timeline OCA)
    lab_date_first_work = fields.Date(
        "Primo giorno lavorato", compute="_compute_lab_execution", store=True,
        help="Data del primo foglio ore sul task.")
    lab_date_last_work = fields.Date(
        "Ultimo giorno lavorato", compute="_compute_lab_execution", store=True,
        help="Data dell'ultimo foglio ore sul task.")
    lab_to_estimate = fields.Boolean(
        "Da stimare", compute="_compute_lab_execution", store=True, index=True,
        help="Manca il tempo stimato o l'inizio/fine pianificati.")
    lab_over_estimate = fields.Boolean(
        "Oltre la stima", compute="_compute_lab_execution", store=True,
        help="Ore registrate superiori al tempo stimato.")
    lab_remaining_estimate = fields.Float(
        "Ore residue (stima)", tracking=True, copy=False,
        help="Quante ore mancano per finire il task, secondo chi ci lavora. Si aggiorna "
             "registrando le ore (colonna Ore residue del foglio ore) o qui dal PM.")
    lab_remaining_date = fields.Date("Ore residue aggiornate il", readonly=True, copy=False)
    lab_eac_hours = fields.Float(
        "Stima a finire (ore)", compute="_compute_lab_forecast", store=True,
        help="Ore registrate + ore residue. Se le ore residue non sono mai state indicate: "
             "il maggiore tra tempo stimato e ore registrate.")
    lab_progress_pct = fields.Float(
        "Avanzamento %", compute="_compute_lab_forecast", store=True, aggregator="avg",
        help="Ore registrate / stima a finire.")
    lab_forecast_over = fields.Boolean(
        "Sforerà la stima", compute="_compute_lab_forecast", store=True, index=True,
        help="La stima a finire supera il tempo stimato: lo si vede prima di sforare.")
    lab_schedule_state = fields.Selection(
        SCHEDULE_STATES, "Avanzamento", compute="_compute_lab_schedule",
        search="_search_lab_schedule_state",
        help="Da stimare: manca stima o pianificazione. Inizio in ritardo: lavoro iniziato "
             "dopo l'inizio pianificato (o non ancora iniziato a data passata). Oltre la data "
             "di fine: aperto dopo la fine pianificata o lavorato dopo di essa.")

    def _lab_is_internal(self):
        """Task del progetto interno (riunioni, formazione, assenze): niente stima né date."""
        self.ensure_one()
        internal = self.sudo().company_id.internal_project_id
        return bool(internal) and self.project_id == internal

    @api.depends("timesheet_ids.date", "timesheet_ids.unit_amount", "allocated_hours",
                 "planned_date_start", "planned_date_end", "effective_hours", "project_id")
    def _compute_lab_execution(self):
        for task in self:
            dates = task.sudo().timesheet_ids.mapped("date")
            task.lab_date_first_work = min(dates) if dates else False
            task.lab_date_last_work = max(dates) if dates else False
            task.lab_to_estimate = not task._lab_is_internal() and (
                not task.allocated_hours or not task.planned_date_start
                or not task.planned_date_end)
            task.lab_over_estimate = bool(task.allocated_hours
                                          and task.effective_hours > task.allocated_hours + 0.01)

    @api.depends("effective_hours", "allocated_hours", "lab_remaining_estimate",
                 "lab_remaining_date", "is_closed")
    def _compute_lab_forecast(self):
        for task in self:
            done = task.effective_hours
            if task.is_closed:
                eac = done
            elif task.lab_remaining_date:
                eac = done + task.lab_remaining_estimate
            else:
                eac = max(task.allocated_hours, done)
            task.lab_eac_hours = eac
            task.lab_progress_pct = (done / eac * 100.0) if eac else (100.0 if task.is_closed else 0.0)
            task.lab_forecast_over = bool(task.allocated_hours
                                          and eac > task.allocated_hours + 0.01)

    def write(self, vals):
        if "lab_remaining_estimate" in vals and "lab_remaining_date" not in vals:
            vals["lab_remaining_date"] = fields.Date.context_today(self)
        res = super().write(vals)
        if "lab_remaining_estimate" in vals or "allocated_hours" in vals:
            self._lab_notify_forecast_over()
        return res

    def _lab_notify_forecast_over(self):
        """Nuovo sforamento previsto: nota nel task e attività al PM (una volta sola)."""
        for task in self.sudo().filtered(lambda t: t.lab_forecast_over and not t.is_closed):
            if task.env.context.get("lab_forecast_notified"):
                continue
            pm = task.project_id.user_id
            summary = "Il task sforerà la stima"
            if pm and not task.activity_ids.filtered(lambda a: a.summary == summary):
                task.with_context(lab_forecast_notified=True).activity_schedule(
                    "mail.mail_activity_data_todo", user_id=pm.id, summary=summary,
                    note=("Stima a finire %.1f ore contro %.1f stimate: rivedi stima, "
                          "pianificazione o accordi con il cliente.") % (
                        task.lab_eac_hours, task.allocated_hours))

    @api.model
    def _lab_recompute_execution(self):
        """All'installazione e agli aggiornamenti: ricalcola i campi salvati della
        consuntivazione (es. task del progetto interno esclusi dai "da stimare")."""
        tasks = self.with_context(active_test=False).search([("project_id", "!=", False)])
        self.env.add_to_compute(self._fields["lab_to_estimate"], tasks)
        self.env.add_to_compute(self._fields["lab_eac_hours"], tasks)
        tasks._recompute_recordset(["lab_date_first_work", "lab_date_last_work",
                                    "lab_to_estimate", "lab_over_estimate", "lab_eac_hours",
                                    "lab_progress_pct", "lab_forecast_over"])

    def _lab_schedule_state_on(self, today):
        self.ensure_one()
        task = self
        if task._lab_is_internal():
            return False
        if task.is_closed:
            return "done"
        if task.lab_to_estimate:
            return "to_estimate"
        start = task.planned_date_start.date()
        end = task.planned_date_end.date()
        if today > end or (task.lab_date_last_work and task.lab_date_last_work > end):
            return "late_end"
        if task.lab_date_first_work:
            return "late_start" if task.lab_date_first_work > start else "on_time"
        return "late_start" if today > start else "not_started"

    @api.depends("is_closed", "lab_to_estimate", "planned_date_start", "planned_date_end",
                 "lab_date_first_work", "lab_date_last_work")
    def _compute_lab_schedule(self):
        today = fields.Date.context_today(self)
        for task in self:
            task.lab_schedule_state = task._lab_schedule_state_on(today)

    def _search_lab_schedule_state(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            raise NotImplementedError(operator)
        values = [value] if isinstance(value, str) else list(value or [])
        today = fields.Date.context_today(self)
        tasks = self.with_context(active_test=False).search([("project_id", "!=", False)])
        ids = [t.id for t in tasks if t._lab_schedule_state_on(today) in values]
        positive = operator in ("=", "in")
        return [("id", "in" if positive else "not in", ids)]
