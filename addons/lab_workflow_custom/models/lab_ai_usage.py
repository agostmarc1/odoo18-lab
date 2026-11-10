"""Fase 2: consumi AI a consumo (API Anthropic, Claude Code) e loro attribuzione.

Fonti dei dati (intercambiabili, stesso risultato):
  - manuale: righe inserite a mano in "Consumi AI";
  - csv: import standard di Odoo dalla lista "Consumi AI" (es. export dalla Console);
  - api: connettore facoltativo all'API Usage & Cost Analytics di Anthropic. In un ambiente
    demo resta spento (nessuna chiave): tutto il resto funziona lo stesso.

Attribuzione (tabella lab.ai.mapping, senza toccare il codice):
  workspace o chiave API dedicati a una commessa -> costo diretto sulla commessa;
  utente (actor) -> persona -> costo ripartito sulle sue ore del mese;
  nessuna corrispondenza -> costi generali.
"""
import logging
from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ANTHROPIC_COST_URL = "https://api.anthropic.com/v1/organizations/analytics/cost"
ANTHROPIC_HEADERS = {
    "anthropic-version": "2026-10-21",
    "anthropic-beta": "analytics-usage-cost-2026-08-24",
    "User-Agent": "odoo18-lab/1.0",
}
KEY_PARAM = "lab_workflow_custom.anthropic_admin_key"

REF_TYPES = [
    ("workspace", "Workspace Anthropic"),
    ("api_key", "Chiave API"),
    ("actor", "Utente Anthropic (actor)"),
]


class LabAiMapping(models.Model):
    """Corrispondenze: chi o cosa del fornitore AI -> commessa o persona."""
    _name = "lab.ai.mapping"
    _description = "Corrispondenza consumi AI"
    _order = "ref_type, name"

    ref_type = fields.Selection(REF_TYPES, "Tipo", required=True, default="workspace")
    name = fields.Char("Identificativo", required=True,
                       help="Es. wrkspc_..., apikey_..., user_... come appaiono nei report "
                            "del fornitore.")
    label = fields.Char("Descrizione")
    project_id = fields.Many2one("project.project", "Commessa",
                                 help="Per workspace e chiavi dedicate: il costo va tutto qui.")
    employee_id = fields.Many2one("hr.employee", "Persona",
                                  help="Per utenti e chiavi personali: il costo si ripartisce "
                                       "sulle commesse in base alle ore della persona.")
    active = fields.Boolean(default=True)

    _sql_constraints = [("ref_unique", "unique(ref_type, name)",
                         "Questo identificativo ha già una corrispondenza.")]

    @api.model_create_multi
    def create(self, vals_list):
        mappings = super().create(vals_list)
        mappings._rematch_usages()
        return mappings

    def write(self, vals):
        res = super().write(vals)
        self._rematch_usages()
        return res

    def _rematch_usages(self):
        """Una nuova corrispondenza vale anche per i consumi già importati
        (ma non per quelli dei mesi già chiusi)."""
        field_by_type = {"workspace": "workspace_ref", "api_key": "api_key_ref",
                         "actor": "actor_ref"}
        Usage = self.env["lab.ai.usage"].sudo()
        closed = self.env["lab.cost.period"].sudo().search([("state", "=", "closed")])
        for mapping in self:
            usages = Usage.search([(field_by_type[mapping.ref_type], "=", mapping.name)])
            usages = usages.filtered(lambda u: not any(
                p.date_start <= u.date <= p.date_end for p in closed))
            usages._compute_target()


class LabAiUsage(models.Model):
    """Una riga di consumo AI (di solito: un giorno × workspace × chiave × utente)."""
    _name = "lab.ai.usage"
    _description = "Consumo AI"
    _order = "date desc, id desc"

    date = fields.Date("Giorno", required=True, default=fields.Date.context_today, index=True)
    source = fields.Selection([("manual", "Manuale"), ("csv", "Import CSV"),
                               ("api", "API Anthropic")], "Fonte", default="manual",
                              required=True)
    tool_id = fields.Many2one("lab.ai.tool", "Strumento",
                              domain="[('tool_type', '=', 'usage')]")
    description = fields.Char("Descrizione", help="Es. modello o prodotto (Claude Code, API).")
    workspace_ref = fields.Char("Workspace", index=True)
    api_key_ref = fields.Char("Chiave API", index=True)
    actor_ref = fields.Char("Utente (actor)", index=True)
    amount_currency = fields.Monetary("Importo fornitore", currency_field="currency_id",
                                      required=True)
    currency_id = fields.Many2one("res.currency", "Valuta", required=True,
                                  default=lambda s: s.env.ref("base.USD", raise_if_not_found=False)
                                  or s.env.company.currency_id)
    amount = fields.Monetary("Importo in valuta aziendale", compute="_compute_amount",
                             store=True, currency_field="company_currency_id")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    project_id = fields.Many2one("project.project", "Commessa", compute="_compute_target",
                                 store=True, readonly=False, index=True)
    employee_id = fields.Many2one("hr.employee", "Persona", compute="_compute_target",
                                  store=True, readonly=False)
    attribution = fields.Selection(
        [("direct", "Diretto sulla commessa"), ("person", "Ripartito sulle ore della persona"),
         ("overhead", "Costi generali")], "Attribuzione", compute="_compute_attribution",
        store=True)
    external_ref = fields.Char("Riferimento import", index=True, copy=False,
                               help="Chiave della riga nel report del fornitore: evita doppioni "
                                    "quando si reimporta.")

    _sql_constraints = [("external_ref_unique", "unique(external_ref, company_id)",
                         "Questa riga di consumo è già stata importata.")]

    @api.depends("amount_currency", "currency_id", "date", "company_id")
    def _compute_amount(self):
        for usage in self:
            usage.amount = usage.currency_id._convert(
                usage.amount_currency, usage.company_id.currency_id, usage.company_id,
                usage.date or fields.Date.today()) if usage.currency_id else 0.0

    @api.depends("workspace_ref", "api_key_ref", "actor_ref")
    def _compute_target(self):
        mappings = self.env["lab.ai.mapping"].sudo().search([])
        index = {(m.ref_type, m.name): m for m in mappings}
        for usage in self:
            project = employee = False
            # ordine: workspace e chiave dedicati vincono sull'utente
            for ref_type, ref in (("workspace", usage.workspace_ref),
                                  ("api_key", usage.api_key_ref),
                                  ("actor", usage.actor_ref)):
                mapping = index.get((ref_type, ref)) if ref else None
                if not mapping:
                    continue
                project = project or mapping.project_id
                employee = employee or mapping.employee_id
            usage.project_id = project
            usage.employee_id = employee

    @api.depends("project_id", "employee_id")
    def _compute_attribution(self):
        for usage in self:
            usage.attribution = ("direct" if usage.project_id
                                 else "person" if usage.employee_id else "overhead")

    def action_rematch(self):
        """Riapplica le corrispondenze (dopo averne aggiunte di nuove)."""
        self._compute_target()
        return True

    # ---- Connettore Anthropic (facoltativo) ------------------------------------
    @api.model
    def _lab_parse_anthropic_rows(self, payload):
        """Converte la risposta di /v1/organizations/analytics/cost in valori di lab.ai.usage.
        Importi: stringhe in centesimi di USD con 6 decimali ("41280.000000" = 412,80 $)."""
        usd = self.env.ref("base.USD")
        tool = self.env.ref("lab_workflow_custom.ai_tool_claude_api", raise_if_not_found=False)
        vals_list = []
        for row in payload.get("data", []):
            group = row.get("group") or {}
            cost = row.get("cost") or {}
            actor = group.get("actor") or {}
            actor_ref = actor.get("user_id") or actor.get("service_account_id") or actor.get("id")
            day = datetime.strptime(row["starting_at"][:10], "%Y-%m-%d").date()
            parts = [row["starting_at"][:10], group.get("workspace_id") or "-",
                     group.get("api_key_id") or "-", actor_ref or "-",
                     group.get("product") or "-", group.get("model") or "-"]
            vals_list.append({
                "date": day,
                "source": "api",
                "tool_id": tool.id if tool else False,
                "description": " / ".join(p for p in (group.get("product"), group.get("model"))
                                          if p) or _("Consumo API"),
                "workspace_ref": group.get("workspace_id") or False,
                "api_key_ref": group.get("api_key_id") or False,
                "actor_ref": actor_ref or False,
                "amount_currency": float(cost.get("amount") or 0) / 100.0,
                "currency_id": usd.id,
                "external_ref": "anthropic|" + "|".join(parts),
            })
        return vals_list

    @api.model
    def _lab_upsert(self, vals_list):
        """Crea o aggiorna (i dati del fornitore si consolidano nei giorni successivi)."""
        created = updated = 0
        for vals in vals_list:
            existing = self.search([("external_ref", "=", vals["external_ref"])], limit=1)
            if existing:
                existing.write({"amount_currency": vals["amount_currency"]})
                updated += 1
            else:
                self.create(vals)
                created += 1
        return created, updated

    @api.model
    def _lab_fetch_anthropic(self, date_from, date_to):
        key = self.env["ir.config_parameter"].sudo().get_param(KEY_PARAM)
        if not key:
            raise UserError(_(
                "Connettore Anthropic non configurato: in questo ambiente (demo) i consumi si "
                "inseriscono a mano o con l'import CSV. Per collegarlo, l'amministratore imposta "
                "la chiave Admin nel parametro di sistema %s.", KEY_PARAM))
        params = {
            "starting_at": f"{date_from.isoformat()}T00:00:00Z",
            "ending_at": f"{date_to.isoformat()}T00:00:00Z",
            "time_bucket_width": "1d",
            "group_by[]": ["workspace_id", "api_key_id", "actor", "product", "model"],
            "limit": 1000,
        }
        headers = dict(ANTHROPIC_HEADERS, **{"x-api-key": key})
        vals_list = []
        for _page in range(100):  # protezione: al massimo 100 pagine
            response = requests.get(ANTHROPIC_COST_URL, params=params, headers=headers,
                                    timeout=60)
            if response.status_code != 200:
                raise UserError(_("Anthropic ha risposto %(code)s: %(text)s",
                                  code=response.status_code, text=response.text[:300]))
            payload = response.json()
            vals_list += self._lab_parse_anthropic_rows(payload)
            if not payload.get("has_more"):
                break
            params["page"] = payload.get("next_page")
        return self._lab_upsert(vals_list)

    @api.model
    def action_import_anthropic(self):
        today = fields.Date.today()
        created, updated = self._lab_fetch_anthropic(today - timedelta(days=30), today)
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Consumi AI importati"),
            "message": _("%(c)s righe nuove, %(u)s aggiornate.", c=created, u=updated),
            "type": "success", "next": {"type": "ir.actions.act_window_close"}}}

    @api.model
    def _cron_import_anthropic(self):
        """Ogni notte: importa gli ultimi 3 giorni se il connettore è configurato."""
        if not self.env["ir.config_parameter"].sudo().get_param(KEY_PARAM):
            return  # ambiente demo: nessun connettore, nessun errore
        today = fields.Date.today()
        try:
            self._lab_fetch_anthropic(today - timedelta(days=3), today)
        except UserError as error:
            _logger.warning("Import consumi Anthropic non riuscito: %s", error)
