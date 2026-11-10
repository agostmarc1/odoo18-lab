# Funzioni comuni agli script (non eseguire direttamente)
set -euo pipefail
# Git Bash su Windows: non convertire i percorsi Linux (/var/lib/odoo...) in percorsi Windows
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Manca il file .env: copia .env.example in .env e imposta le password."; exit 1; }
set -a; . ./.env; set +a
DB=lab18
# Si installa SOLO la nostra app: Odoo installa da solo tutti i moduli standard e OCA da cui dipende
MODULES="lab_workflow_custom"
# Localizzazione italiana: configurazione dell'AMBIENTE (non è una personalizzazione, quindi non è
# una dipendenza dell'app). Tutti i moduli OCA l10n-italy 18.0; le loro dipendenze arrivano da sole.
ITALY_MODULES="l10n_it_abicab,l10n_it_accompanying_invoice,l10n_it_account,\
l10n_it_account_invoice_start_end_dates,l10n_it_account_stamp,\
l10n_it_account_vat_period_end_settlement,l10n_it_amount_to_text,l10n_it_appointment_code,\
l10n_it_asset_management,l10n_it_ateco,l10n_it_bill_of_entry,l10n_it_central_journal_reportlab,\
l10n_it_currency_rate_update_boi,l10n_it_delivery_note,l10n_it_delivery_note_batch,\
l10n_it_delivery_note_customer_code,l10n_it_delivery_note_order_link,\
l10n_it_edi_accompanying_invoice,l10n_it_edi_doi_extension,l10n_it_edi_doi_extension_vat_registry,\
l10n_it_edi_extension,l10n_it_edi_pec,l10n_it_edi_related_document,l10n_it_edi_sdi,\
l10n_it_edi_sender_partner,l10n_it_edi_td29,l10n_it_financial_statement_eu,\
l10n_it_financial_statements_report,l10n_it_fiscalcode_sale,l10n_it_intrastat,\
l10n_it_intrastat_statement,l10n_it_location_nuts,l10n_it_pos_fiscalcode,l10n_it_riba_oca,\
l10n_it_vat_registries,l10n_it_vat_settlement_communication,l10n_it_vat_settlement_date,\
l10n_it_website_portal_fiscalcode"
odoo_run() {  # esegue un comando odoo "una tantum" senza il server web
  docker compose run --rm -T odoo odoo "$@" --no-http --stop-after-init
}
odoo_shell() {  # esegue codice Python (da stdin) nella shell di Odoo
  docker compose run --rm -T -e LAB_ADMIN_PASSWORD -e LAB_USERS_PASSWORD odoo \
    odoo shell -d "$DB" --no-http
}
setup_company_italy() {
  # Va fatto PRIMA di installare la contabilità: dopo, Odoo non permette di cambiare valuta.
  odoo_shell <<'PY'
company = env.ref('base.main_company')
eur = env.ref('base.EUR')
eur.active = True
company.write({
    'name': 'Software House Lab S.r.l.',
    'country_id': env.ref('base.it').id,
    'currency_id': eur.id,
    'city': 'Milano',
})
# I tassi demo di base sono stati caricati quando l'azienda era in USD: vanno riallineati
# all'euro (EUR = 1). Il cambio USD qui sotto e' DIMOSTRATIVO (1,08 USD per 1 EUR); per i
# cambi reali si attiva il modulo l10n_it_currency_rate_update_boi (Banca d'Italia).
Rate = env['res.currency.rate']
Rate.search([('company_id', 'in', [company.id, False])]).unlink()
Rate.create({'currency_id': env.ref('base.USD').id, 'company_id': company.id,
             'name': '2026-01-01', 'rate': 1.08})
lang = env['res.lang']._activate_lang('it_IT')
company.partner_id.lang = 'it_IT'
env.ref('base.user_admin').write({'lang': 'it_IT', 'tz': 'Europe/Rome'})
usd = env.ref('base.USD')
if not env['res.company'].search_count([('currency_id', '=', usd.id)]):
    usd.active = False  # resta disponibile (es. consumi Anthropic in dollari), ma non in evidenza
env.cr.commit()
print("Azienda impostata: Italia, euro, lingua italiana.")
PY
}
finalize_companies() {
  # Dopo l'installazione: i dati demo standard rinominano l'azienda principale e aggiungono
  # aziende demo (es. "Chicago" in dollari). Nome di nuovo nostro, e tutto in euro dove
  # non ci sono ancora movimenti contabili.
  odoo_shell <<'PY'
eur = env.ref('base.EUR')
env.ref('base.main_company').name = 'Software House Lab S.r.l.'
for company in env['res.company'].search([('currency_id', '!=', eur.id)]):
    if env['account.move.line'].search_count([('company_id', '=', company.id)]):
        print("ATTENZIONE: %s ha movimenti in %s, valuta non cambiata" % (company.name, company.currency_id.name))
        continue
    company.currency_id = eur
usd = env.ref('base.USD')
if not env['res.company'].search_count([('currency_id', '=', usd.id)]):
    usd.active = False
# Conti bancari aziendali dei dati demo: in un'azienda vera li verifica l'Amministrazione;
# senza verifica Odoo 18 non permette di confermare le fatture che li riportano.
companies = env['res.company'].search([])
banks = env['res.partner.bank'].search([('partner_id', 'in', companies.partner_id.ids),
                                        ('allow_out_payment', '=', False)])
banks.with_user(env.ref('base.user_admin')).allow_out_payment = True  # la verifica la fa l'amministratore
env.cr.commit()
print("Conti bancari aziendali verificati:", len(banks))
print("Aziende:", "; ".join("%s (%s)" % (c.name, c.currency_id.name) for c in env['res.company'].search([])))
PY
}
set_passwords() {
  # admin + tutti gli utenti di prova creati dalla nostra app (dati demo)
  odoo_shell <<'PY'
import os
users = env['res.users'].sudo()
users.browse(env.ref('base.user_admin').id).password = os.environ['LAB_ADMIN_PASSWORD']
demo_ids = env['ir.model.data'].search([
    ('module', '=', 'lab_workflow_custom'), ('model', '=', 'res.users')]).mapped('res_id')
for user in users.browse(demo_ids).exists():
    user.password = os.environ['LAB_USERS_PASSWORD']
env.cr.commit()
print("Password impostate:", ", ".join(users.browse(demo_ids).exists().mapped('login')))
PY
}
