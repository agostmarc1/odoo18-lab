# Funzioni comuni agli script (non eseguire direttamente)
set -euo pipefail
# Git Bash su Windows: non convertire i percorsi Linux (/var/lib/odoo...) in percorsi Windows
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Manca il file .env: copia .env.example in .env e imposta le password."; exit 1; }
set -a; . ./.env; set +a
DB=lab18
MODULES="crm,sale_management,project,hr_timesheet,sale_timesheet,account,subscription_oca,project_timeline,lab_workflow_custom"
odoo_run() {  # esegue un comando odoo "una tantum" senza il server web
  docker compose run --rm -T odoo odoo "$@" --no-http --stop-after-init
}
set_passwords() {
  docker compose run --rm -T -e LAB_ADMIN_PASSWORD -e LAB_USERS_PASSWORD odoo \
    odoo shell -d "$DB" --no-http <<'PY'
import os
users = env['res.users'].sudo()
users.browse(env.ref('base.user_admin').id).password = os.environ['LAB_ADMIN_PASSWORD']
for login in ('commerciale', 'pm', 'analista', 'sviluppatore', 'amministrazione'):
    u = users.search([('login', '=', login)])
    if u:
        u.password = os.environ['LAB_USERS_PASSWORD']
env.cr.commit()
print("Password impostate.")
PY
}
