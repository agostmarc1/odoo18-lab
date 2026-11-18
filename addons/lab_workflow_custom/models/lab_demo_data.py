"""Dati sintetici della software house: uno scenario coerente per verificare a colpo d'occhio
che l'app funzioni (monte ore, T&M con consulente e pass-through, canone AMS, sviluppo a corpo,
pianificazione 80/20, ore parallele, costi AI, chiusura del mese, margini, ticket di assistenza).

Non parte mai da solo in un database di produzione: si carica
- con i dati demo dell'app (demo/demo_synthetic.xml), oppure
- su richiesta: ``env["lab.demo.data"]._lab_load_synthetic()`` (lo fa scripts/init_db.sh).
È idempotente: se lo scenario c'è già non fa nulla. Le date sono relative a oggi
(mese scorso / mese in corso), così i dati restano sempre "freschi".
"""
import logging
from datetime import date, datetime, time, timedelta

from odoo import api, fields, models, tools

_logger = logging.getLogger(__name__)

MODULE = "lab_workflow_custom"
MARKER = "synth_order_rossi"
FILLER_NAME = "Attività interne (riunioni, formazione)"


def _workdays(start, end):
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


class LabDemoData(models.AbstractModel):
    _name = "lab.demo.data"
    _description = "Dati sintetici della software house"

    # ---- utilità -----------------------------------------------------------------
    def _ref(self, name):
        return self.env.ref(f"{MODULE}.{name}")

    def _xmlid(self, name, record):
        self.env["ir.model.data"].create({
            "module": MODULE, "name": name, "model": record._name,
            "res_id": record.id, "noupdate": True})
        return record

    def _load_master_files(self):
        """Utenti, persone e licenze AI: gli stessi file dei dati demo dell'app."""
        if self.env.ref(f"{MODULE}.user_marco", raise_if_not_found=False):
            return
        for path in ("demo/demo_users.xml", "demo/demo_costs.xml"):
            tools.convert_file(self.env, MODULE, path, {}, mode="init", noupdate=True,
                               kind="demo")

    @api.model
    def _lab_load_synthetic(self):
        if self.env.ref(f"{MODULE}.{MARKER}", raise_if_not_found=False):
            # scenario caricato con una versione precedente dell'app: aggiunge solo i ticket
            loaded = self._lab_load_helpdesk()
            loaded = self._lab_load_portal_users() or loaded
            loaded = self._lab_load_project_history() or loaded
            loaded = self._lab_load_timesheet_check() or loaded
            loaded = self._lab_load_winery() or loaded
            loaded = self._lab_load_vertical() or loaded
            if loaded:
                return True
            _logger.info("Dati sintetici già presenti: nulla da fare")
            return False
        self = self.sudo().with_context(tracking_disable=True, mail_notrack=True,
                                        mail_create_nolog=True)
        self._load_master_files()
        self.env.invalidate_all()
        ctx = self._context_data()
        self._crm(ctx)
        self._orders(ctx)
        self._previous_month(ctx)
        self._current_month(ctx)
        self._planning(ctx)
        self._lab_load_portal_users()
        self.env["lab.cost.period"]._cron_compute_open_periods()
        self._lab_load_project_history()
        self._lab_load_timesheet_check()
        self._lab_load_winery()
        self._lab_load_vertical()
        _logger.info("Dati sintetici caricati")
        return True

    # ---- contesto: persone, date ----------------------------------------------------
    def _context_data(self):
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        prev_end = month_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        users = {k: self._ref(x) for k, x in {
            "giuseppe": "user_giuseppe", "marco": "user_marco", "carlo": "user_carlo",
            "niccolo": "user_niccolo", "giulia": "user_giulia", "gianluca": "user_gianluca",
            "nicola": "user_nicola", "luana": "user_amministrazione"}.items()}
        emp = {k: u.employee_id for k, u in users.items() if u.employee_id}
        prev_days = _workdays(prev_start, prev_end)
        cur_days = _workdays(month_start, today) or [today]
        return {"today": today, "month_start": month_start, "prev_start": prev_start,
                "prev_end": prev_end, "prev_days": prev_days, "cur_days": cur_days,
                "users": users, "emp": emp}

    def _lab_load_timesheet_check(self):
        """Consuntivazione di esempio: orario part-time per Giulia, due giorni di ferie per
        Gianluca, giornate completate con attività interne e alcune ore mancanti volute
        (Carlo ieri, Giulia un giorno della settimana scorsa, Niccolò due settimane fa).
        Sui task: stime e date pianificate, un task in ritardo e alcuni da stimare. Idempotente."""
        if (self.env.ref(f"{MODULE}.synth_calendar_part_time", raise_if_not_found=False)
                or not self.env.ref(f"{MODULE}.{MARKER}", raise_if_not_found=False)):
            return False
        env = self.env(su=True, context=dict(self.env.context, tracking_disable=True,
                                             mail_notrack=True, mail_create_nolog=True,
                                             leave_skip_state_check=True))
        today = fields.Date.context_today(self)
        admin = env.ref("base.user_admin").employee_id
        admin.lab_timesheet_required = False
        people = {key: self._ref(f"user_{key}").employee_id
                  for key in ("carlo", "gianluca", "giulia", "marco", "niccolo", "nicola")}
        # Giulia part-time: 4 ore al mattino, dal lunedì al venerdì
        calendar = env["resource.calendar"].create({
            "name": "Part-time 20 ore (mattino)", "hours_per_day": 4.0,
            "attendance_ids": [(0, 0, {"name": f"Mattino {d}", "dayofweek": str(d),
                                       "hour_from": 9.0, "hour_to": 13.0,
                                       "day_period": "morning"}) for d in range(5)]})
        self._xmlid("synth_calendar_part_time", calendar)
        people["giulia"].resource_calendar_id = calendar
        # Gianluca in ferie giovedì e venerdì della settimana scorsa (richiesta approvata)
        last_monday = today - timedelta(days=today.weekday() + 7)
        leave_type = env.ref("hr_holidays.holiday_status_cl")
        allocation = env["hr.leave.allocation"].create({
            "name": "Ferie dell'anno", "holiday_status_id": leave_type.id,
            "employee_id": people["gianluca"].id, "number_of_days": 20,
            "date_from": today.replace(month=1, day=1)})
        allocation.action_validate()
        leave = env["hr.leave"].create({
            "name": "Ferie", "holiday_status_id": leave_type.id,
            "employee_id": people["gianluca"].id,
            "request_date_from": last_monday + timedelta(days=3),
            "request_date_to": last_monday + timedelta(days=4)})
        leave.action_validate()
        # giornate completate con attività interne, tranne le ore mancanti volute
        internal = env.company.internal_project_id
        internal_task = internal.task_ids.filtered(lambda t: t.name == "Formazione")[:1] \
            or internal.task_ids[:1]
        Day = env["lab.timesheet.day"]
        start = today - timedelta(days=62)
        Day._lab_refresh(start, today, admin.browse([e.id for e in people.values()]))
        carlo_day = Day._lab_previous_workday(people["carlo"], today)
        gaps = {(people["carlo"].id, carlo_day): 3.0,
                (people["giulia"].id, last_monday + timedelta(days=2)): None,  # tutto il giorno
                (people["niccolo"].id, last_monday - timedelta(days=6)): 2.0}
        lines = []
        for row in Day.search([("employee_id", "in", [e.id for e in people.values()]),
                               ("date", ">=", start)]):
            missing = row.missing_hours
            gap = gaps.get((row.employee_id.id, row.date), 0.0)
            hours = 0.0 if gap is None else max(missing - gap, 0.0)
            if hours > 0.01:
                lines.append({"name": FILLER_NAME,
                              "project_id": internal.id, "task_id": internal_task.id,
                              "employee_id": row.employee_id.id, "date": row.date,
                              "unit_amount": hours})
        env["account.analytic.line"].with_context(lab_skip_parallel=True).create(lines)
        Day._lab_refresh(start, today)
        # task: stime e date pianificate (un task in ritardo, alcuni da stimare)
        def plan(task, begin, end):
            task.write({"planned_date_start": datetime.combine(begin, time(8, 0)),
                        "planned_date_end": datetime.combine(end, time(17, 0))})
        for task in env["project.task"].search([("project_id", "not in", internal.ids),
                                               ("project_id", "!=", False),
                                               ("allocated_hours", ">", 0)]):
            if task.name.startswith("Test") and "Portale" in task.project_id.name:
                continue  # da stimare: mancano le date
            if task.name.startswith("Project Management") and "sinistri" in task.project_id.name:
                continue  # da stimare: mancano le date
            begin = task.lab_date_first_work or today - timedelta(days=10)
            end = max(begin + timedelta(days=max(int(task.allocated_hours // 6), 3)),
                      today + timedelta(days=7))
            if task.name.startswith("Sviluppo integrazione corrieri"):
                end = today - timedelta(days=3)  # oltre la data di fine
            if task.name.startswith("Test") and "sinistri" in task.project_id.name:
                begin, end = today - timedelta(days=2), today + timedelta(days=10)  # in ritardo
            plan(task, begin, end)
        self._lab_demo_remaining(env)
        return True

    def _lab_demo_remaining(self, env):
        """Ore residue indicate da chi lavora: un task sforerà la stima, gli altri sono in linea."""
        today = fields.Date.context_today(self)
        for task in env["project.task"].search([("allocated_hours", ">", 0),
                                               ("project_id", "!=", False)]):
            if task.name.startswith("Sviluppo - Sviluppo Software"):
                remaining = task.allocated_hours - task.effective_hours + 12  # sforerà di 12 ore
            elif task.effective_hours:
                remaining = max(task.allocated_hours - task.effective_hours, 2.0)
            else:
                continue
            task.write({"lab_remaining_estimate": remaining, "lab_remaining_date": today})

    def _lab_load_project_history(self):
        """Cronologia di esempio nel chatter dei progetti demo: ordini, fatture e ticket già
        presenti (con la loro data), più per la commessa Neri un SAL, una call fatta, un incontro
        in calendario e il prossimo SAL da fare. Idempotente."""
        if (self.env.ref(f"{MODULE}.synth_project_update_neri", raise_if_not_found=False)
                or not self.env.ref(f"{MODULE}.{MARKER}", raise_if_not_found=False)):
            return False
        from markupsafe import Markup
        from .lab_project_history import _link
        env = self.env(su=True)
        marco = self._ref("user_marco")
        author = marco.partner_id

        def note(project, body, when):
            msg = project.with_context(mail_create_nosubscribe=True).message_post(
                body=body, message_type="comment", subtype_xmlid="mail.mt_note",
                author_id=author.id)
            msg.date = when

        orders = env["sale.order"].search([("state", "=", "sale")])
        for order in orders:
            for project in order._lab_projects():
                note(project, Markup("🧾 <b>Ordine di vendita confermato</b>: %s – %s, "
                                     "imponibile %s") % (
                    _link(order, order.name), order.partner_id.display_name,
                    tools.format_amount(env, order.amount_untaxed, order.currency_id)),
                    order.date_order)
        for move in env["account.move"].search([("state", "=", "posted"), (
                "move_type", "in", ("out_invoice", "in_invoice"))]):
            label = "📤 <b>Fattura cliente emessa</b>" if move.move_type == "out_invoice" \
                else "📥 <b>Fattura fornitore registrata</b>"
            for project, amount in move._lab_project_amounts().items():
                note(project, Markup(label + ": %s – %s, imponibile su questa commessa %s") % (
                    _link(move, move.name), move.partner_id.display_name,
                    tools.format_amount(env, amount, move.currency_id)),
                    move.invoice_date or move.date)
        for ticket in env["helpdesk.ticket"].search([("project_id", "!=", False)]):
            note(ticket.project_id, Markup("🎫 <b>Ticket aperto</b>: %s %s") % (
                _link(ticket, ticket.number), ticket.name), ticket.create_date)

        neri = self._ref("synth_order_neri")._lab_projects()[:1]
        if not neri:
            return True
        today = fields.Datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        # call fatta (attività Chiamata segnata come fatta: Odoo la scrive nel chatter)
        call = neri.with_user(marco).activity_schedule(
            "mail.mail_activity_data_call", date_deadline=today.date() - timedelta(days=6),
            summary="Call di avvio con il referente IT di Neri", user_id=marco.id)
        call.with_user(marco).action_feedback(
            feedback="Confermato il perimetro delle API sinistri; il cliente invia i tracciati "
                     "entro venerdì.")
        # SAL (aggiornamento di stato della Dashboard: finisce anche nel chatter)
        update = env["project.update"].with_user(marco).create({
            "name": "SAL 1 – analisi conclusa", "project_id": neri.id, "status": "on_track",
            "progress": 30, "user_id": marco.id,
            "description": Markup("<ul><li>Analisi funzionale approvata dal cliente</li>"
                                  "<li>Sviluppo avviato sul modulo denunce</li>"
                                  "<li>Rischio: tracciati del vecchio gestionale in ritardo"
                                  "</li></ul>")})
        self._xmlid("synth_project_update_neri", update)
        # incontro in calendario e prossimo SAL da fare
        start = today + timedelta(days=7 - today.weekday() + 1)
        env["calendar.event"].with_user(marco).with_context(no_mail_to_attendees=True).create({
            "name": "Incontro di avanzamento con Neri Assicurazioni",
            "start": start, "stop": start + timedelta(hours=1), "user_id": marco.id,
            "res_model_id": env["ir.model"]._get_id("project.project"), "res_id": neri.id,
            "partner_ids": [(6, 0, (author | neri.partner_id).ids)]})
        neri.with_user(marco).activity_schedule(
            f"{MODULE}.mail_activity_type_sal", date_deadline=(start + timedelta(days=14)).date(),
            summary="SAL 2 con il cliente", user_id=marco.id)
        return True

    # ---- Cliente cantina: pacchetto Odoo chiavi in mano con l'assistente Claude -----------
    def _lab_free_hours(self, employee, day):
        """Ore ancora libere nel giorno (ore attese meno ore su commesse e ticket) e righe di
        "Attività interne" di riempimento che si possono ridurre per far posto al lavoro."""
        internal = self.env.company.internal_project_id
        lines = self.env["account.analytic.line"].search([
            ("employee_id", "=", employee.id), ("date", "=", day), ("project_id", "!=", False)])
        filler = lines.filtered(lambda l: l.project_id == internal and l.name == FILLER_NAME)
        row = self.env["lab.timesheet.day"].search(
            [("employee_id", "=", employee.id), ("date", "=", day)], limit=1)
        due = row.due_hours if row else (employee.resource_calendar_id.hours_per_day or 8.0)
        return due - sum((lines - filler).mapped("unit_amount")), filler

    def _lab_ts_fit(self, ctx, who, task, day, hours, name):
        """Foglio ore che non crea ore parallele: usa solo le ore libere del giorno, togliendole
        dalle attività interne di riempimento. Restituisce la riga creata (o niente)."""
        employee = ctx["emp"][who]
        free, filler = self._lab_free_hours(employee, day)
        hours = min(hours, free)
        if hours <= 0.01:
            return self.env["account.analytic.line"]
        rest = hours
        for line in filler.with_context(lab_skip_parallel=True):
            take = min(line.unit_amount, rest)
            if take >= line.unit_amount - 0.01:
                line.unlink()
            else:
                line.unit_amount -= take
            rest -= take
            if rest <= 0.01:
                break
        return self._ts(ctx, who, task, day, hours, name)

    def _lab_load_winery(self):
        """Cantina Bricco Rosso (Barolo, circa 80.000 bottiglie l'anno), cliente della software
        house per il pacchetto "Odoo chiavi in mano per cantine" con il modulo langhe_wine_ai
        (ordini da email con Claude, Packing List export). Ciclo completo nel mese in corso:
        opportunità vinta, ordine a corpo confermato, commessa con task stimati, ore di PM,
        analisi e del consulente Carlo (sviluppo con Claude Code), consumo API dedicato alla
        commessa, cronologia nel chatter e preventivo del canone di assistenza dopo il go-live.
        Le ore usano solo il tempo libero delle persone: nessuna ora parallela nuova.
        Idempotente."""
        if (self.env.ref(f"{MODULE}.synth_order_bricco", raise_if_not_found=False)
                or not self.env.ref(f"{MODULE}.{MARKER}", raise_if_not_found=False)):
            return False
        from markupsafe import Markup
        from .lab_project_history import _link
        self = self.sudo().with_context(tracking_disable=True, mail_notrack=True,
                                        mail_create_nolog=True)
        ctx = self._context_data()
        users, today = ctx["users"], ctx["today"]
        giuseppe, marco = users["giuseppe"], users["marco"]
        days = [d for d in ctx["cur_days"] if d < today] or [today]
        day = lambda i: days[min(i, len(days) - 1)]  # noqa: E731

        # Commerciale: cliente, opportunità e ordine a prezzo fisso
        partner = self._partner("synth_partner_bricco", "Cantina Bricco Rosso S.r.l. Agricola",
                                "Barolo", "info@briccorosso.example")
        partner.write({"user_id": giuseppe.id, "street": "Via delle Langhe 12", "zip": "12060"})
        lead = self.env["crm.lead"].create({
            "name": "Odoo chiavi in mano per la cantina con assistente Claude",
            "type": "opportunity", "partner_id": partner.id, "user_id": giuseppe.id,
            "expected_revenue": 12000 + 12 * 1500,  # setup + primo anno di assistenza
            "description": Markup(
                "<p>80.000 bottiglie l'anno, 40% export (USA, Germania, Svizzera). Oggi ordini "
                "da email e WhatsApp ricopiati a mano, listini in Excel. Registri SIAN nel "
                "software di cantina: restano lì.</p>")})
        self._xmlid("synth_lead_bricco", lead)
        dev = self._ref("product_dev_fixed").product_variant_id
        order = self.env["sale.order"].with_user(giuseppe).create({
            "partner_id": partner.id, "opportunity_id": lead.id,
            "client_order_ref": "Setup Odoo cantina – prezzo fisso",
            "order_line": [(0, 0, {
                "product_id": dev.id, "product_uom_qty": 1,
                "name": "Setup chiavi in mano Odoo 18 CE per cantina: vini, annate e lotti, "
                        "listini Privati / Ho.Re.Ca. / Export USA, DDT e Packing List, punto "
                        "vendita ed eventi di degustazione, modulo langhe_wine_ai (ordini da "
                        "email con Claude)"})]})
        order.with_user(giuseppe).action_confirm()
        order = order.sudo()
        order.date_order = fields.Datetime.to_datetime(days[0])
        self._xmlid("synth_order_bricco", order)
        lead.action_set_won()
        line = order.order_line[:1]
        project = line.task_id.project_id or line.project_id
        project.user_id = marco
        dev_task = line.task_id or self._task(project, "Sviluppo")
        dev_task.name = "Sviluppo modulo langhe_wine_ai e configurazione"

        # Analisti, PM e consulente: ore del mese in corso (solo tempo libero)
        fit = self._lab_ts_fit
        fit(ctx, "marco", self._task(project, "Project"), day(0), 2,
            "Kick-off in cantina a Barolo con il titolare")
        fit(ctx, "gianluca", self._task(project, "Analisi"), day(0), 4,
            "Sopralluogo: flusso ordini, listini e lotti")
        fit(ctx, "gianluca", self._task(project, "Analisi"), day(1), 6,
            "Specifica listini Privati, Ho.Re.Ca. ed Export USA")
        fit(ctx, "gianluca", self._task(project, "Analisi"), day(2), 4,
            "Raccordo con il software SIAN: codice prodotto + lotto")
        fit(ctx, "carlo", dev_task, day(2), 6,
            "Modulo langhe_wine_ai: anagrafica vino e Packing List con Claude Code")
        fit(ctx, "carlo", dev_task, day(3), 6,
            "Analisi ordini da email con Claude: prompt, schema JSON e test")
        fit(ctx, "gianluca", self._task(project, "Test"), day(4), 3,
            "Prova con 15 email reali di importatori")
        fit(ctx, "marco", self._task(project, "Project"), day(4), 1,
            "Stato avanzamento con la cantina")

        # Costi AI: workspace API dedicato alla commessa (costo diretto)
        self._xmlid("synth_mapping_bricco", self.env["lab.ai.mapping"].create({
            "ref_type": "workspace", "name": "wrkspc_bricco_rosso",
            "label": "Workspace API della commessa Cantina Bricco Rosso",
            "project_id": project.id}))
        self.env["lab.ai.usage"].create({
            "date": day(3), "source": "manual", "tool_id": self._ref("ai_tool_claude_api").id,
            "currency_id": self.env.ref("base.USD").id, "amount_currency": 26.40,
            "workspace_ref": "wrkspc_bricco_rosso",
            "description": "API / claude-sonnet-5-5 – prove di analisi ordini da email",
            "external_ref": "synth|bricco|1"})

        # PM: date dei task, stima a finire, cronologia e prossimi passi
        go_live = today + timedelta(days=21)
        for task in project.task_ids.filtered(lambda t: t.allocated_hours > 0):
            task.write({"planned_date_start": datetime.combine(days[0], time(8, 0)),
                        "planned_date_end": datetime.combine(go_live, time(17, 0))})
            if task.effective_hours:
                task.write({"lab_remaining_estimate": max(
                    task.allocated_hours - task.effective_hours, 2.0),
                    "lab_remaining_date": today})
        msg = project.with_context(mail_create_nosubscribe=True).message_post(
            body=Markup("🧾 <b>Ordine di vendita confermato</b>: %s – %s, imponibile %s") % (
                _link(order, order.name), partner.display_name,
                tools.format_amount(self.env, order.amount_untaxed, order.currency_id)),
            message_type="comment", subtype_xmlid="mail.mt_note", author_id=marco.partner_id.id)
        msg.date = fields.Datetime.to_datetime(days[0])
        start = datetime.combine(day(0), time(8, 0))  # 9:00 ora italiana (UTC+1)
        self.env["calendar.event"].with_user(marco).with_context(
            no_mail_to_attendees=True).create({
                "name": "Sopralluogo in cantina a Barolo", "start": start,
                "stop": start + timedelta(hours=3), "user_id": marco.id,
                "res_model_id": self.env["ir.model"]._get_id("project.project"),
                "res_id": project.id,
                "partner_ids": [(6, 0, (marco.partner_id | partner).ids)]})
        project.with_user(marco).activity_schedule(
            "mail.mail_activity_data_todo", date_deadline=go_live,
            summary="Formazione in cantina e go-live", user_id=marco.id)

        # Commerciale: canone di assistenza dopo il go-live (preventivo in bozza)
        quote = self.env["sale.order"].with_user(giuseppe).create({
            "partner_id": partner.id, "opportunity_id": lead.id,
            "client_order_ref": "Assistenza dedicata dopo il go-live",
            "order_line": [(0, 0, {"product_id": self._ref(
                "product_ams_monthly").product_variant_id.id, "product_uom_qty": 1})]})
        self._xmlid("synth_quote_bricco", quote.sudo())

        self.env["lab.timesheet.day"]._lab_refresh(ctx["month_start"], today)
        self.env["lab.cost.period"]._cron_compute_open_periods()
        _logger.info("Cliente cantina (Cantina Bricco Rosso) caricato")
        return True

    # Modello di progetto della Soluzione Cantina: le fasi standard di ogni installazione (60 h)
    VERTICAL_STEPS = [
        ("Raccolta dati: vini, listini, clienti e utenti nei file del cliente", 8),
        ("Istanza dedicata e caricamento dati (nuovo_cliente.sh)", 4),
        ("Configurazione standard: listini, lotti, cartoni, DDT", 10),
        ("Personalizzazioni leggere (stampe, campi)", 12),
        ("Formazione in cantina: titolare, commerciale, magazzino", 12),
        ("Go-live e affiancamento", 8),
        ("Project management", 6),
    ]

    def _lab_load_vertical(self):
        """Soluzione Cantina: dopo la prima cantina (Bricco Rosso, 120 h su misura) la software
        house la trasforma in un'offerta standard da proporre ad altre cantine. Crea la soluzione
        di settore, il modello di progetto con le fasi standard (60 h), i prodotti a listino
        (setup a prezzo fisso e canone), collega Bricco Rosso come installazione pilota (con
        l'indirizzo del suo Odoo dedicato) e apre una seconda trattativa con l'offerta standard.
        Idempotente."""
        if (self.env.ref(f"{MODULE}.synth_vertical_cantina", raise_if_not_found=False)
                or not self.env.ref(f"{MODULE}.synth_order_bricco", raise_if_not_found=False)):
            return False
        from markupsafe import Markup
        self = self.sudo().with_context(tracking_disable=True, mail_notrack=True,
                                        mail_create_nolog=True)
        ctx = self._context_data()
        users, today = ctx["users"], ctx["today"]
        giuseppe, marco = users["giuseppe"], users["marco"]

        vertical = self._xmlid("synth_vertical_cantina", self.env["lab.vertical"].create({
            "name": "Soluzione Cantina (Langhe)", "user_id": marco.id,
            "description": Markup(
                "<p>Odoo 18 Community dedicato per cantine da 30.000 a 150.000 bottiglie:</p><ul>"
                "<li>vendite, magazzino con lotti e cartoni, acquisti, CRM, eventi in cantina;</li>"
                "<li>listini Italia, Ho.Re.Ca., Export Europa ed Export USA;</li>"
                "<li>modulo <b>langhe_wine_ai</b>: ordini da email con Claude, schede tecniche "
                "IT/EN/DE, Packing List export;</li>"
                "<li>installazione ripetibile: <code>verticali/cantine/nuovo_cliente.sh</code> "
                "con i file del cliente (vini.csv, clienti.csv).</li></ul>"
                "<p>Fuori perimetro: registri telematici SIAN/ICQRF (restano nel software di "
                "cantina).</p>"),
        }))
        template = self._xmlid("synth_project_template_cantina", self.env["project.project"].create({
            "name": "MODELLO – Soluzione Cantina", "user_id": marco.id,
            "privacy_visibility": "followers", "allow_timesheets": True,
            "description": Markup("<p>Modello di progetto: non segnare ore qui. Ogni ordine del "
                                  "setup standard ne crea una copia con queste fasi.</p>")}))
        for seq, (name, hours) in enumerate(self.VERTICAL_STEPS, 1):
            self.env["project.task"].create({
                "name": name, "project_id": template.id, "allocated_hours": hours,
                "sequence": seq * 10, "user_ids": False})
        standard_hours = sum(h for _n, h in self.VERTICAL_STEPS)
        unit = self.env.ref("uom.product_uom_unit").id
        common = {"type": "service", "sale_ok": True, "purchase_ok": False,
                  "uom_id": unit, "uom_po_id": unit,
                  "service_policy": "ordered_prepaid", "lab_vertical_id": vertical.id}
        setup = self._xmlid("synth_product_cantina_setup", self.env["product.template"].create(dict(
            common, name="Soluzione Cantina – setup chiavi in mano", default_code="CANT-SETUP",
            list_price=9000, service_tracking="project_only", project_template_id=template.id,
            lab_hours_per_unit=standard_hours,
            description_sale="Odoo 18 CE dedicato per la cantina con la Soluzione Cantina standard: "
                             "installazione, caricamento di vini, listini e clienti, formazione e "
                             "go-live. Prezzo fisso, %d ore stimate." % standard_hours)))
        ams = self._xmlid("synth_product_cantina_ams", self.env["product.template"].create(dict(
            common, name="Soluzione Cantina – assistenza e aggiornamenti", default_code="CANT-AMS",
            list_price=450, service_tracking="project_only", lab_monthly_hours=6,
            subscribable=True, subscription_template_id=self._ref("subscription_template_monthly").id,
            description_sale="Canone mensile: assistenza, aggiornamenti della soluzione e "
                             "hosting gestito, 6 ore/mese incluse.")))

        # Prima installazione (pilota): Bricco Rosso, con l'indirizzo del suo Odoo dedicato
        bricco = self._ref("synth_order_bricco")
        line = bricco.order_line[:1]
        project = line.task_id.project_id or line.project_id
        project.write({"lab_vertical_id": vertical.id, "lab_instance_url": "http://127.0.0.1:8070"})
        self._ref("synth_lead_bricco").write({
            "lab_vertical_id": vertical.id, "expected_revenue": 12000 + 12 * 450})
        quote = self._ref("synth_quote_bricco")
        if quote.state == "draft":  # il canone della cantina diventa quello standard del settore
            quote.order_line.filtered(lambda l: l.product_id.lab_monthly_hours)[:1].write({
                "product_id": ams.product_variant_id.id})

        # Commerciale: seconda cantina in trattativa con l'offerta standard
        partner = self._partner("synth_partner_noci", "Tenuta Collina dei Noci S.s. Agricola",
                                "La Morra", "info@collinadeinoci.example")
        partner.user_id = giuseppe
        stages = self.env["crm.stage"].search([("is_won", "=", False)], order="sequence")
        lead = self._xmlid("synth_lead_noci", self.env["crm.lead"].create({
            "name": "Soluzione Cantina standard – 45.000 bottiglie, export in Germania",
            "type": "opportunity", "partner_id": partner.id, "user_id": giuseppe.id,
            "lab_vertical_id": vertical.id, "expected_revenue": 9000 + 12 * 450,
            "stage_id": stages[min(2, len(stages) - 1)].id if stages else False,
            "description": Markup(
                "<p>Ha visto la demo della Soluzione Cantina sull'Odoo di Bricco Rosso. Oggi "
                "listini in Excel e ordini dei distributori tedeschi ricopiati a mano.</p>")}))
        # due documenti, come per Bricco Rosso: setup a prezzo fisso e canone dopo il go-live
        # (nello stesso ordine il canone farebbe trattare anche il setup come contratto mensile)
        for xmlid, ref, product in (
                ("synth_quote_noci", "Soluzione Cantina standard – setup", setup),
                ("synth_quote_noci_ams", "Soluzione Cantina – assistenza dopo il go-live", ams)):
            offer = self.env["sale.order"].with_user(giuseppe).create({
                "partner_id": partner.id, "opportunity_id": lead.id, "client_order_ref": ref,
                "order_line": [(0, 0, {"product_id": product.product_variant_id.id,
                                       "product_uom_qty": 1})]})
            self._xmlid(xmlid, offer.sudo())
        lead.with_user(giuseppe).activity_schedule(
            "mail.mail_activity_data_todo", date_deadline=today + timedelta(days=3),
            summary="Demo in cantina con l'Odoo di Bricco Rosso", user_id=giuseppe.id)
        vertical.with_context(mail_create_nosubscribe=True).message_post(
            body=Markup("Prima installazione: <b>%s</b>, %d h a corpo su misura. Da qui il "
                        "setup standard da %d h con il modello di progetto.") % (
                bricco.partner_id.name, line.lab_sold_hours, standard_hours),
            message_type="comment", subtype_xmlid="mail.mt_note", author_id=marco.partner_id.id)
        _logger.info("Soluzione di settore Cantina caricata")
        return True

    def _lab_load_portal_users(self):
        """Clienti con accesso al portale (Kanban dei ticket): Mario Verdi per Verdi Retail e
        Luca Rossi per Rossi Meccanica. Password da .env (scripts/_lib.sh set_passwords, che
        prende tutti gli utenti con xmlid di questa app). Idempotente."""
        if (self.env.ref(f"{MODULE}.synth_user_portal_verdi", raise_if_not_found=False)
                or not self.env.ref(f"{MODULE}.{MARKER}", raise_if_not_found=False)):
            return False
        self = self.sudo()
        portal = self.env.ref("base.group_portal")
        for key, company_xmlid, name, login in (
                ("verdi", "synth_partner_verdi", "Mario Verdi", "mario.verdi@verdiretail.example"),
                ("rossi", "synth_partner_rossi", "Luca Rossi", "luca.rossi@rossimeccanica.example")):
            company = self._ref(company_xmlid)
            contact = self.env["res.partner"].create({
                "name": name, "parent_id": company.id, "email": login, "lang": self._lang()})
            user = self.env["res.users"].with_context(no_reset_password=True).create({
                "name": name, "login": login, "email": login, "partner_id": contact.id,
                "groups_id": [(6, 0, [portal.id])]})
            self._xmlid(f"synth_user_portal_{key}", user)
        _logger.info("Utenti portale dei clienti creati")
        return True

    def _lang(self):
        """Italiano se installato, altrimenti la lingua attiva (su un Odoo nuovo: inglese)."""
        installed = [code for code, _n in self.env["res.lang"].get_installed()]
        return "it_IT" if "it_IT" in installed else (self.env.lang or installed[0])

    def _partner(self, xmlid, name, city, email):
        partner = self.env["res.partner"].create({
            "name": name, "is_company": True, "country_id": self.env.ref("base.it").id,
            "city": city, "email": email, "lang": self._lang()})
        return self._xmlid(xmlid, partner)

    # ---- CRM: opportunità aperte del Commerciale ------------------------------------
    def _crm(self, ctx):
        Lead = self.env["crm.lead"]
        stages = self.env["crm.stage"].search([], order="sequence")
        giuseppe = ctx["users"]["giuseppe"]
        opportunities = [
            ("Gialli Software S.r.l.", "Torino", "Portale B2B per i rivenditori", 18000, 0),
            ("Blu Energia S.p.A.", "Bologna", "Assistenza applicativa AMS 2027", 18000, 1),
            ("Viola Moda S.r.l.", "Firenze", "Integrazione e-commerce e magazzino", 9500, 2),
        ]
        for i, (name, city, title, revenue, stage_idx) in enumerate(opportunities, 1):
            partner = self._partner(f"synth_partner_lead_{i}", name, city,
                                    f"info@{name.split()[0].lower()}.example")
            lead = Lead.create({
                "name": title, "type": "opportunity", "partner_id": partner.id,
                "user_id": giuseppe.id, "expected_revenue": revenue,
                "stage_id": stages[min(stage_idx, len(stages) - 1)].id if stages else False})
            self._xmlid(f"synth_lead_{i}", lead)
        # preventivo in bozza collegato all'opportunità AMS
        lead = self._ref("synth_lead_2")
        quote = self.env["sale.order"].with_user(giuseppe).create({
            "partner_id": lead.partner_id.id, "opportunity_id": lead.id,
            "client_order_ref": "Offerta AMS 2027",
            "order_line": [(0, 0, {"product_id": self._ref(
                "product_ams_monthly").product_variant_id.id, "product_uom_qty": 1})]})
        self._xmlid("synth_quote_blu", quote.sudo())

    # ---- Ordini confermati il mese scorso ---------------------------------------------
    def _make_order(self, ctx, xmlid, partner, product_xmlid, qty, ref):
        giuseppe = ctx["users"]["giuseppe"]
        order = self.env["sale.order"].with_user(giuseppe).create({
            "partner_id": partner.id, "client_order_ref": ref,
            "order_line": [(0, 0, {"product_id": self._ref(product_xmlid).product_variant_id.id,
                                   "product_uom_qty": qty})]})
        order.with_user(giuseppe).action_confirm()
        order = order.sudo()
        order.date_order = fields.Datetime.to_datetime(ctx["prev_days"][0])
        line = order.order_line[:1]
        project = line.task_id.project_id or line.project_id
        project.user_id = ctx["users"]["marco"]
        self._xmlid(xmlid, order)
        return order, project

    def _orders(self, ctx):
        rossi = self._partner("synth_partner_rossi", "Rossi Meccanica S.r.l.", "Brescia",
                              "amministrazione@rossimeccanica.example")
        bianchi = self._partner("synth_partner_bianchi", "Bianchi Logistica S.p.A.", "Verona",
                                "it@bianchilogistica.example")
        verdi = self._partner("synth_partner_verdi", "Verdi Retail S.r.l.", "Milano",
                              "helpdesk@verdiretail.example")
        neri = self._partner("synth_partner_neri", "Neri Assicurazioni S.p.A.", "Roma",
                             "progetti@neriassicurazioni.example")
        ctx["rossi"] = self._make_order(ctx, MARKER, rossi, "product_hours_pack_50", 1,
                                   "Portale clienti – monte ore 50h")
        ctx["bianchi"] = self._make_order(ctx, "synth_order_bianchi", bianchi, "product_tm_hourly",
                                     60, "Integrazione corrieri – a consuntivo")
        ctx["bianchi"][0].order_line.task_id.name = "Sviluppo integrazione corrieri"
        ctx["verdi"] = self._make_order(ctx, "synth_order_verdi", verdi, "product_ams_monthly", 1,
                                   "Assistenza applicativa mensile")
        ctx["neri"] = self._make_order(ctx, "synth_order_neri", neri, "product_dev_fixed", 1,
                                  "Gestionale sinistri – sviluppo a corpo")
        # Assistenza: ticket dell'Helpdesk (il canone AMS di Verdi li riceve in automatico)
        ctx["tickets"] = self._helpdesk(ctx)
        # Corrispondenze dei consumi AI
        Mapping = self.env["lab.ai.mapping"]
        self._xmlid("synth_mapping_bianchi", Mapping.create({
            "ref_type": "workspace", "name": "wrkspc_bianchi_integrazione",
            "label": "Workspace API dedicato alla commessa Bianchi",
            "project_id": ctx["bianchi"][1].id}))
        self._xmlid("synth_mapping_carlo", Mapping.create({
            "ref_type": "actor", "name": "user_carlo_claude_code",
            "label": "Claude Code di Carlo", "employee_id": ctx["emp"]["carlo"].id}))

    # ---- fogli ore -------------------------------------------------------------------
    def _task(self, project, prefix):
        return project.task_ids.filtered(lambda t: t.name.startswith(prefix))[:1]

    def _ts(self, ctx, who, task, day, hours, name):
        return self.env["account.analytic.line"].create({
            "name": name, "project_id": task.project_id.id, "task_id": task.id,
            "employee_id": ctx["emp"][who].id, "unit_amount": hours, "date": day})

    def _ts_ticket(self, ctx, who, ticket, day, hours, name):
        """Ore segnate sul ticket: la commessa (canone AMS) arriva dal ticket."""
        return self.env["account.analytic.line"].create({
            "name": name, "ticket_id": ticket.id, "employee_id": ctx["emp"][who].id,
            "unit_amount": hours, "date": day})

    def _post(self, ctx, move):
        move.with_user(ctx["users"]["luana"]).action_post()
        return move

    # ---- Assistenza: ticket dell'Helpdesk ------------------------------------------------
    def _helpdesk(self, ctx):
        """Ticket di Verdi Retail (canone AMS, commessa collegata in automatico) e uno di Rossi
        (monte ore: la commessa la sceglie il Supporto). Copre tutti gli stati: chiusi con
        valutazione, in corso, in attesa del cliente, urgente con SLA scaduto, da smistare."""
        users = ctx["users"]
        team = self._ref("helpdesk_team_support")
        team.write({"user_ids": [(4, users["nicola"].id)], "user_id": users["nicola"].id})
        verdi = ctx["verdi"][0].partner_id
        rossi = ctx["rossi"][0].partner_id
        (verdi | rossi).user_id = users["giuseppe"]  # venditore: vede i ticket dei suoi clienti
        ref = self.env.ref
        stage = {k: ref(f"helpdesk_mgmt.helpdesk_ticket_stage_{k}")
                 for k in ("new", "in_progress", "awaiting", "done")}
        channel = {k: ref(f"helpdesk_mgmt.helpdesk_ticket_channel_{k}") for k in ("email", "web")}
        kind = {k: self._ref(f"helpdesk_type_{k}") for k in ("bug", "question", "change")}
        area = {k: self._ref(f"helpdesk_category_{k}")
                for k in ("access", "sales", "stock", "reports")}
        d, cur, today = ctx["prev_days"], ctx["cur_days"], ctx["today"]
        at = lambda day, hour=9: fields.Datetime.to_datetime(day).replace(hour=hour - 1)  # noqa: E731  (UTC)
        now = fields.Datetime.now()
        # chiave, cliente, titolo, descrizione, tipo, area, priorità, canale,
        # aperto il, stadio finale, chiuso il, valutazione (1-5)
        specs = [
            ("ddt", verdi, "Errore nella stampa dei DDT",
             "Stampando il DDT del cliente Bianchi compare un errore e il PDF non si genera.",
             "bug", "stock", "2", "email", at(d[1]), "done", at(d[12], 16), 5),
            ("utente", verdi, "Nuovo utente per il magazzino",
             "Serve un accesso per il nuovo magazziniere, Luca Gialli, con i permessi di Mario.",
             "question", "access", "1", "web", at(d[4], 10), "done", at(d[6], 11), 4),
            ("report", verdi, "Report vendite lento a fine mese",
             "Il report vendite mensile impiega più di 5 minuti ad aprirsi.",
             "bug", "reports", "1", "email", at(d[7], 11), "done", at(d[10], 15), 3),
            ("listini", verdi, "Esportazione listini verso l'e-commerce",
             "Vorremmo esportare in automatico i listini verso il sito e-commerce ogni notte.",
             "change", "sales", "2", "web", now - timedelta(days=1), "in_progress", False, False),
            ("import", verdi, "Errore nell'import degli ordini da Excel",
             "L'import degli ordini da Excel si ferma alla riga 120 con un errore sulle date.",
             "bug", "sales", "1", "email", now - timedelta(days=1, hours=-1), "awaiting", False, False),
            ("etichette", verdi, "Etichette di spedizione disallineate",
             "Le etichette del corriere escono spostate di qualche millimetro.",
             "bug", "stock", "1", "email", at(cur[0], 9), "done",
             at(cur[min(1, len(cur) - 1)], 17), 5),
            ("fatture", verdi, "Bloccata l'emissione delle fatture elettroniche",
             "Da stamattina l'invio delle fatture allo SdI va in errore: non riusciamo a fatturare.",
             "bug", "sales", "3", "web", now - timedelta(days=2), "new", False, False),
            ("rossi", rossi, "Come esporto l'elenco dei clienti?",
             "Ci servirebbe l'elenco dei clienti del portale in Excel con l'ultima data di accesso.",
             "question", "sales", "1", "email", now - timedelta(hours=3), "new", False, False),
        ]
        tickets = {}
        for (key, partner, name, desc, kind_k, area_k, prio, chan, opened, final, closed,
             score) in specs:
            ticket = self.env["helpdesk.ticket"].create({
                "name": name, "description": f"<p>{desc}</p>", "partner_id": partner.id,
                "team_id": team.id, "type_id": kind[kind_k].id, "category_id": area[area_k].id,
                "priority": prio, "channel_id": channel[chan].id})
            # data di apertura nel passato (mai nel futuro), poi SLA ricalcolati da quella data
            opened = min(opened, now - timedelta(minutes=30))
            self.env.cr.execute("UPDATE helpdesk_ticket SET create_date = %s WHERE id = %s",
                                (opened, ticket.id))
            ticket.invalidate_recordset(["create_date"])
            ticket.set_sla()
            if final != "new":
                ticket.write({"user_id": users["nicola"].id, "stage_id": stage[final].id})
                # storia già avvenuta: gli stadi raggiunti lo sono stati in tempo (il ritardo
                # dello scenario è solo sul ticket urgente ancora da prendere in carico)
                reached = ticket.ticket_sla_ids.filtered(
                    lambda s: ticket.stage_id.sequence >= s.expected_stage_id.sequence)
                reached.write({"state": "accomplished"})
                (ticket.ticket_sla_ids - reached).filtered(
                    lambda s: s.state == "expired").write({"state": "in_progress"})
            if closed:
                closed = max(min(closed, now), opened)
                ticket.write({"closed_date": closed, "last_stage_update": closed})
                ticket.ticket_sla_ids.write({"last_state_date": closed})
            if score:
                self.env["rating.rating"].create({
                    "res_model_id": self.env["ir.model"]._get_id("helpdesk.ticket"),
                    "res_id": ticket.id, "partner_id": partner.id,
                    "rated_partner_id": users["nicola"].partner_id.id, "rating": score,
                    "consumed": True, "feedback": "Risposta rapida e chiara, grazie!"
                    if score >= 4 else "Risolto, ma ci è voluto un po'."})
            tickets[key] = self._xmlid(f"synth_ticket_{key}", ticket)
        return tickets

    @api.model
    def _lab_load_helpdesk(self):
        """Database con lo scenario già caricato (prima dei ticket): crea i ticket e sposta le
        ore dei vecchi task "Ticket 101–103" di Verdi sui ticket, poi elimina quei task.
        Idempotente: se i ticket ci sono già non fa nulla."""
        if (self.env.ref(f"{MODULE}.synth_ticket_ddt", raise_if_not_found=False)
                or not self.env.ref(f"{MODULE}.{MARKER}", raise_if_not_found=False)):
            return False
        self = self.sudo().with_context(tracking_disable=True, mail_notrack=True,
                                        mail_create_nolog=True)
        ctx = self._context_data()
        for key, xmlid in (("rossi", MARKER), ("verdi", "synth_order_verdi")):
            order = self._ref(xmlid)
            line = order.order_line[:1]
            ctx[key] = (order, line.task_id.project_id or line.project_id)
        tickets = self._helpdesk(ctx)
        old_tasks = ctx["verdi"][1].task_ids.filtered(
            lambda t: t.name.startswith("Ticket 10")).sorted("name")
        # mese scorso -> i tre ticket chiusi del mese scorso; mese in corso -> ticket "etichette"
        # (chiuso a inizio mese), così le ore restano dopo l'apertura del ticket
        targets = [("ddt", "etichette"), ("utente", "etichette"), ("report", "etichette")]
        for task, (prev_key, cur_key) in zip(old_tasks, targets):
            for line in task.timesheet_ids:
                key = prev_key if line.date < ctx["month_start"] else cur_key
                line.with_context(lab_skip_parallel=True).write(
                    {"ticket_id": tickets[key].id, "task_id": False})
            task.unlink()
        _logger.info("Ticket di assistenza caricati (%s task convertiti)", len(old_tasks))
        return True

    # ---- Mese scorso: lavoro, fatture, consumi AI, chiusura --------------------------------
    def _previous_month(self, ctx):
        d = ctx["prev_days"]
        rossi, p_rossi = ctx["rossi"]
        bianchi, p_bianchi = ctx["bianchi"]
        neri, p_neri = ctx["neri"]
        ts = self._ts
        # Rossi (monte ore 50h)
        ts(ctx, "giulia", self._task(p_rossi, "Analisi"), d[1], 4, "Workshop requisiti")
        ts(ctx, "giulia", self._task(p_rossi, "Analisi"), d[2], 3, "Specifica funzionale")
        ts(ctx, "marco", self._task(p_rossi, "Project"), d[1], 2, "Kick-off con il cliente")
        ts(ctx, "marco", self._task(p_rossi, "Project"), d[10], 1, "Stato avanzamento")
        for i, h in ((4, 8), (5, 8), (6, 6)):
            ts(ctx, "niccolo", self._task(p_rossi, "Sviluppo"), d[i], h, "Sviluppo area clienti")
        ts(ctx, "gianluca", self._task(p_rossi, "Test"), d[12], 3, "Piano di test")
        # Bianchi (T&M): analisi interna fatturata a ore, sviluppo del consulente Carlo
        ts(ctx, "giulia", self._task(p_bianchi, "Sviluppo"), d[3], 4, "Analisi tracciati corrieri")
        ts(ctx, "giulia", self._task(p_bianchi, "Sviluppo"), d[4], 4, "Mappatura dati")
        ts(ctx, "giulia", self._task(p_bianchi, "Sviluppo"), d[8], 8, "Specifiche tecniche API")
        ts(ctx, "giulia", self._task(p_bianchi, "Sviluppo"), d[9], 8, "Test con i corrieri")
        for i in (5, 6, 7):
            ts(ctx, "carlo", self._task(p_bianchi, "Sviluppo"), d[i], 8,
               "Connettore API corrieri con Claude Code")
        # Neri (a corpo 120h): analisi quasi esaurita
        for i, h in ((8, 8), (9, 6), (11, 3)):
            ts(ctx, "gianluca", self._task(p_neri, "Analisi"), d[i], h, "Analisi processi sinistri")
        ts(ctx, "marco", self._task(p_neri, "Project"), d[8], 2, "Kick-off")
        # Verdi (AMS): ticket del mese scorso
        for i, (t, h) in enumerate([("ddt", 4), ("utente", 1), ("report", 5), ("ddt", 3)]):
            self._ts_ticket(ctx, "nicola", ctx["tickets"][t], d[2 + i * 3], h, "Assistenza")

        # Fatture dei consulenti (ultimo giorno del mese), confermate dall'Amministrazione
        product = self._ref("product_external_consultant").product_variant_id
        for who, project, hours, rate, num in (("carlo", p_bianchi, 24, 45, "Fattura 21/2026"),
                                               ("niccolo", p_rossi, 22, 35, "Fattura 8/2026")):
            emp = ctx["emp"][who]
            bill = self.env["account.move"].create({
                "move_type": "in_invoice", "partner_id": emp.lab_vendor_id.id,
                "invoice_date": ctx["prev_end"], "ref": num,
                "invoice_line_ids": [(0, 0, {
                    "product_id": product.id, "quantity": hours, "price_unit": rate,
                    "name": "Consulenza %s – %s" % (emp.name, project.name),
                    "analytic_distribution": {str(project.account_id.id): 100},
                    "lab_consultant_id": emp.id, "tax_ids": [(6, 0, [])]})]})
            self._post(ctx, bill)
            self._xmlid(f"synth_bill_{who}", bill)

        # Consumi AI del mese scorso: diretto, per persona, costi generali (USD)
        api_tool = self._ref("ai_tool_claude_api")
        usd = self.env.ref("base.USD")
        Usage = self.env["lab.ai.usage"]
        for i, (vals, amount) in enumerate([
                ({"workspace_ref": "wrkspc_bianchi_integrazione",
                  "description": "API / claude-sonnet-5-5"}, 84.0),
                ({"actor_ref": "user_carlo_claude_code",
                  "description": "claude_code / claude-opus-5-5"}, 120.0),
                ({"api_key_ref": "apikey_non_censita",
                  "description": "API / claude-haiku-5-5 (chiave non censita)"}, 15.0)], 1):
            Usage.create(dict(vals, date=d[min(5 + i * 4, len(d) - 1)], source="csv",
                              tool_id=api_tool.id, currency_id=usd.id,
                              amount_currency=amount, external_ref=f"synth|prev|{i}"))

        # Chiusura del mese (Amministrazione): ripartizione esatta e spese vive AI sul T&M
        period = self.env["lab.cost.period"]._get_or_create(ctx["prev_start"])
        # le giornate di esempio si completano dopo (_lab_load_timesheet_check): chiusura forzata
        period.with_user(ctx["users"]["luana"]).with_context(lab_force_close=True).action_close()

        # Fatture clienti: monte ore anticipato e T&M del mese scorso
        for order in (rossi, bianchi):
            invoice = order.with_user(ctx["users"]["giuseppe"])._create_invoices()
            invoice = invoice.sudo()
            invoice.invoice_date = ctx["prev_end"]
            self._post(ctx, invoice)

    # ---- Mese in corso -------------------------------------------------------------------
    def _current_month(self, ctx):
        days = ctx["cur_days"]
        today = ctx["today"]
        p_rossi, p_bianchi = ctx["rossi"][1], ctx["bianchi"][1]
        p_neri = ctx["neri"][1]
        ts = self._ts
        first = days[0]
        # Rossi: siamo all'80% del monte ore -> alert giallo
        ts(ctx, "gianluca", self._task(p_rossi, "Test"), first, 2, "Test di accettazione")
        # Giulia in parallelo su due commesse (10h su 8): il PM approva
        a = ts(ctx, "giulia", self._task(p_bianchi, "Sviluppo"), first, 6, "Collaudo con il cliente")
        b = ts(ctx, "giulia", self._task(p_rossi, "Analisi"), first, 4, "Revisione specifica")
        (a | b).with_user(ctx["users"]["marco"]).action_lab_approve_parallel()
        # Oggi: Gianluca e Carlo in parallelo, ancora da approvare
        ts(ctx, "gianluca", self._task(p_bianchi, "Sviluppo"), today, 5, "Test integrazione")
        ts(ctx, "gianluca", self._task(p_neri, "Analisi"), today, 4, "Revisione requisiti")
        ts(ctx, "carlo", self._task(p_bianchi, "Sviluppo"), today, 6, "Gestione errori API")
        ts(ctx, "carlo", self._task(p_neri, "Sviluppo"), today, 6, "Prototipo con Claude Code")
        # AMS del mese: 12h su 20 (60%)
        # (etichette: ticket chiuso a inizio mese; listini e import: aperti ieri, ore di oggi)
        for t, h, day in (("etichette", 3, days[0]), ("etichette", 2, days[min(1, len(days) - 1)]),
                          ("listini", 5, today), ("import", 2, today)):
            self._ts_ticket(ctx, "nicola", ctx["tickets"][t], day, h, "Assistenza")
        # Consumo API del mese in corso, dedicato alla commessa T&M
        self.env["lab.ai.usage"].create({
            "date": today, "source": "manual", "tool_id": self._ref("ai_tool_claude_api").id,
            "currency_id": self.env.ref("base.USD").id, "amount_currency": 38.40,
            "workspace_ref": "wrkspc_bianchi_integrazione",
            "description": "API / claude-opus-5-5", "external_ref": "synth|cur|1"})

    # ---- Pianificazione della settimana (regola 80/20 e fattore parallelo) -----------------
    def _planning(self, ctx):
        today = ctx["today"]
        monday = today - timedelta(days=today.weekday())
        Slot = self.env["lab.planning.slot"]
        p_bianchi, p_neri = ctx["bianchi"][1], ctx["neri"][1]
        dev_neri = self._task(p_neri, "Sviluppo")
        # Niccolò: 32h sulla commessa a corpo (limite pieno con fattore 1,0)
        slots = Slot.create([{"employee_id": ctx["emp"]["niccolo"].id, "project_id": p_neri.id,
                              "task_id": dev_neri.id, "date": monday + timedelta(days=i),
                              "allocated_hours": 8} for i in range(4)])
        slots.action_publish()
        done = slots.filtered(lambda s: s.date < today)
        done.with_user(ctx["users"]["marco"]).action_confirm()
        # Carlo: fattore 1,5 -> fino a 48h; turni pubblicati sulla commessa T&M
        Slot.create([{"employee_id": ctx["emp"]["carlo"].id, "project_id": p_bianchi.id,
                      "task_id": self._task(p_bianchi, "Sviluppo").id,
                      "date": monday + timedelta(days=i), "allocated_hours": 9.6}
                     for i in range(3)]).action_publish()
        # Giulia: settimana prossima, in bozza
        Slot.create([{"employee_id": ctx["emp"]["giulia"].id, "project_id": p_neri.id,
                      "task_id": self._task(p_neri, "Analisi").id,
                      "date": monday + timedelta(days=7 + i), "allocated_hours": 6}
                     for i in range(2)])
        # Il PM abbassa il fattore di Carlo la settimana prossima (formazione)
        self.env["lab.planning.capacity"].create({
            "employee_id": ctx["emp"]["carlo"].id, "week_start": monday + timedelta(days=7),
            "parallel_factor": 1.2, "note": "Giovedì formazione interna"})
