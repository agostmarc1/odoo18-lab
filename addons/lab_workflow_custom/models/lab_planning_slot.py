from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

DEFAULT_MAX_WEEKLY_HOURS = 32.0  # Regola 80/20: 80% di 40h


class LabPlanningSlot(models.Model):
    """Turno pianificato: il PM alloca ore di un dipendente su un task;
    il dipendente conferma il turno e Odoo crea il Foglio Ore."""
    _name = "lab.planning.slot"
    _description = "Turno di pianificazione"
    _inherit = ["mail.thread"]
    _order = "date desc, employee_id"

    name = fields.Char("Descrizione", compute="_compute_name", store=True, readonly=False)
    employee_id = fields.Many2one("hr.employee", "Dipendente", required=True, tracking=True,
                                  index=True)
    user_id = fields.Many2one(related="employee_id.user_id", store=True, string="Utente")
    project_id = fields.Many2one("project.project", "Progetto", required=True, tracking=True)
    task_id = fields.Many2one("project.task", "Task", tracking=True,
                              domain="[('project_id', '=', project_id)]")
    date = fields.Date("Giorno", required=True, default=fields.Date.context_today,
                       tracking=True)
    week_start = fields.Date("Settimana (lunedì)", compute="_compute_week", store=True)
    allocated_hours = fields.Float("Ore pianificate", required=True, default=8.0,
                                   tracking=True)
    confirmed_hours = fields.Float(
        "Ore effettive", help="Ore realmente lavorate: il dipendente può correggerle "
        "prima di confermare. Se 0 si usano le ore pianificate.")
    state = fields.Selection([
        ("draft", "Bozza"),
        ("published", "Pubblicato"),
        ("confirmed", "Confermato"),
        ("cancel", "Annullato"),
    ], default="draft", required=True, tracking=True, string="Stato")
    timesheet_id = fields.Many2one("account.analytic.line", "Foglio ore", readonly=True,
                                   copy=False)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company,
                                 required=True)
    color = fields.Integer(compute="_compute_color")
    # Limite reale della settimana per la persona (32h x fattore parallelo), mostrato nel turno
    weekly_limit = fields.Float("Limite settimanale (ore)", compute="_compute_weekly_load")
    weekly_factor = fields.Float("Fattore parallelo della settimana",
                                 compute="_compute_weekly_load", digits=(4, 2))
    weekly_planned = fields.Float("Già pianificate nella settimana (ore)",
                                  compute="_compute_weekly_load")

    _sql_constraints = [
        ("positive_hours", "CHECK(allocated_hours > 0)",
         "Le ore pianificate devono essere maggiori di zero."),
    ]

    @api.depends("project_id", "task_id")
    def _compute_name(self):
        for slot in self:
            slot.name = slot.task_id.name or slot.project_id.name or _("Turno")

    @api.depends("date")
    def _compute_week(self):
        for slot in self:
            slot.week_start = slot.date - timedelta(days=slot.date.weekday()) if slot.date else False

    @api.depends("state")
    def _compute_color(self):
        colors = {"draft": 0, "published": 4, "confirmed": 10, "cancel": 1}
        for slot in self:
            slot.color = colors.get(slot.state, 0)

    @api.onchange("task_id")
    def _onchange_task_id(self):
        if self.task_id:
            self.project_id = self.task_id.project_id

    @api.model
    def _max_weekly_hours(self):
        value = self.env["ir.config_parameter"].sudo().get_param(
            "lab_workflow_custom.max_weekly_hours")
        return float(value) if value else DEFAULT_MAX_WEEKLY_HOURS

    # ---- Regola 80/20 (con fattore parallelo) -------------------------------
    def _weekly_limit(self, employee, week):
        """Ore-progetto pianificabili: 80% del tempo × fattore parallelo della persona
        (correggibile dal PM settimana per settimana)."""
        override = self.env["lab.planning.capacity"].sudo().search(
            [("employee_id", "=", employee.id), ("week_start", "=", week)], limit=1)
        factor = override.parallel_factor if override else (
            employee.sudo().lab_parallel_factor or 1.0)
        return self._max_weekly_hours() * factor, factor

    @api.depends("employee_id", "week_start", "allocated_hours", "state")
    def _compute_weekly_load(self):
        for slot in self:
            if not slot.employee_id or not slot.week_start:
                slot.update({"weekly_limit": 0.0, "weekly_factor": 0.0, "weekly_planned": 0.0})
                continue
            limit, factor = self._weekly_limit(slot.employee_id, slot.week_start)
            others = self.sudo().search([
                ("employee_id", "=", slot.employee_id.id),
                ("week_start", "=", slot.week_start),
                ("state", "!=", "cancel"),
                ("id", "!=", slot._origin.id or 0),
            ])
            own = slot.allocated_hours if slot.state != "cancel" else 0.0
            slot.update({"weekly_limit": limit, "weekly_factor": factor,
                         "weekly_planned": sum(others.mapped("allocated_hours")) + own})

    @api.constrains("employee_id", "date", "allocated_hours", "state")
    def _check_weekly_capacity(self):
        for slot in self.filtered(lambda s: s.state != "cancel"):
            week = slot.week_start
            limit, factor = self._weekly_limit(slot.employee_id, week)
            total = sum(self.sudo().search([
                ("employee_id", "=", slot.employee_id.id),
                ("week_start", "=", week),
                ("state", "!=", "cancel"),
            ]).mapped("allocated_hours"))
            if total > limit + 1e-6:
                raise ValidationError(_(
                    "Regola 80/20: %(emp)s avrebbe %(tot).1fh pianificate nella settimana "
                    "del %(week)s, ma il massimo è %(max).1fh (80%% del tempo × fattore "
                    "parallelo %(f).2f). Il restante 20%% è riservato a formazione, supporto "
                    "e imprevisti.",
                    emp=slot.employee_id.name, tot=total,
                    week=week.strftime("%d/%m/%Y"), max=limit, f=factor))

    # ---- Permessi sui campi ---------------------------------------------
    def _is_planning_manager(self):
        return self.env.user.has_group("lab_workflow_custom.group_lab_planning_manager")

    def write(self, vals):
        if not self.env.su and not self._is_planning_manager():
            if set(vals) - {"confirmed_hours"}:
                raise AccessError(_("Solo il Project Manager può modificare i turni. "
                                    "Puoi correggere solo le 'Ore effettive' e confermare."))
            if any(s.state != "published" for s in self):
                raise AccessError(_("Puoi modificare solo turni pubblicati e non confermati."))
        return super().write(vals)

    # ---- Azioni -----------------------------------------------------------
    def action_publish(self):
        for slot in self.filtered(lambda s: s.state == "draft"):
            slot.state = "published"
            if slot.user_id:
                slot.message_subscribe(partner_ids=slot.user_id.partner_id.ids)
                slot.message_post(
                    body=_("Nuovo turno: %(d)s, %(h).1fh su %(n)s",
                           d=slot.date.strftime("%d/%m/%Y"), h=slot.allocated_hours,
                           n=slot.name),
                    partner_ids=slot.user_id.partner_id.ids)

    def action_confirm(self):
        """Conferma turno -> crea automaticamente la riga del Foglio Ore."""
        is_manager = self._is_planning_manager()
        for slot in self:
            if slot.state != "published":
                raise UserError(_("Si possono confermare solo i turni pubblicati."))
            if not is_manager and slot.user_id != self.env.user:
                raise AccessError(_("Puoi confermare solo i tuoi turni."))
            hours = slot.confirmed_hours or slot.allocated_hours
            timesheet = self.env["account.analytic.line"].sudo().create({
                "name": _("Turno pianificato: %s", slot.name),
                "date": slot.date,
                "employee_id": slot.employee_id.id,
                "project_id": slot.project_id.id,
                "task_id": slot.task_id.id,
                "unit_amount": hours,
            })
            slot.sudo().write({"state": "confirmed", "timesheet_id": timesheet.id,
                               "confirmed_hours": hours})

    def action_cancel(self):
        for slot in self:
            if slot.timesheet_id:
                raise UserError(_("Il turno è già consuntivato: elimina prima la riga "
                                  "del foglio ore."))
        self.write({"state": "cancel"})

    def action_reset_draft(self):
        self.filtered(lambda s: s.state in ("published", "cancel")).write({"state": "draft"})

    def action_open_timesheet(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.analytic.line",
            "res_id": self.timesheet_id.id,
            "view_mode": "form",
        }
