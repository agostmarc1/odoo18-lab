"""Registra il video dimostrativo dell'app "Flusso Operativo Software House".

Guida un vero browser (Chrome, con Playwright) sugli utenti demo di lab18 e salva il video in
addons/lab_workflow_custom/static/description/demo_flusso_operativo.mp4, insieme all'immagine
di copertina e ai minuti dei capitoli (video_capitoli.json).

Uso:  ./scripts/registra_video.sh            (registra il video)
      ./scripts/registra_video.sh --prova    (solo schermate di controllo, nessun video)

Il video crea un ordine di prova per il cliente "Ferri Automazione S.r.l." con il suo progetto,
un turno e un foglio ore, più un ticket aperto dal modulo web pubblico per Verdi Retail
("Stampa delle bolle bloccata"). A ogni avvio lo script cancella prima quelli della volta precedente
(via XML-RPC come amministratore), così lo scenario sintetico resta pulito.
Le password si leggono da .env: nessuna credenziale in questo file.
"""
import base64
import json
import pathlib
import shutil
import subprocess
import sys
import time
import xmlrpc.client
from datetime import date

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
DESC = ROOT / "addons" / "lab_workflow_custom" / "static" / "description"
WORK = ROOT / "dist" / "video_lavoro"          # dist/ e' gitignored
FRAMES = WORK / "fotogrammi"
URL = "http://127.0.0.1:8069"
DB = "lab18"
CLIENTE = "Ferri Automazione S.r.l."
TICKET_VIDEO = "Stampa delle bolle bloccata"   # ticket aperto dal modulo web nel video
EMAIL_AMS = "helpdesk@verdiretail.example"       # Verdi Retail, canone AMS dei dati sintetici
PROVA = "--prova" in sys.argv
W, H = 1280, 720

ENV = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
           if "=" in line and not line.lstrip().startswith("#"))
PWD_USERS = ENV["LAB_USERS_PASSWORD"].strip()
PWD_ADMIN = ENV["LAB_ADMIN_PASSWORD"].strip()


# ---------------------------------------------------------------- XML-RPC (preparazione)
class Rpc:
    def __init__(self):
        common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
        self.uid = common.authenticate(DB, "admin", PWD_ADMIN, {})
        if not self.uid:
            raise SystemExit("Login XML-RPC come admin non riuscito: controlla LAB_ADMIN_PASSWORD")
        self.obj = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

    def __call__(self, model, method, *args, **kw):
        return self.obj.execute_kw(DB, self.uid, PWD_ADMIN, model, method, list(args), kw)

    def search(self, model, domain, **kw):
        return self(model, "search", domain, **kw)


def pulisci_dati_video(rpc):
    """Toglie ordine, progetto, turni, fogli ore e ticket creati da una registrazione precedente."""
    tickets = rpc.search("helpdesk.ticket", [("name", "=", TICKET_VIDEO)],
                         context={"active_test": False})
    if tickets:
        lines = rpc.search("account.analytic.line", [("ticket_id", "in", tickets)])
        if lines:
            rpc("account.analytic.line", "unlink", lines)
        mails = rpc.search("mail.mail", [("model", "=", "helpdesk.ticket"), ("res_id", "in", tickets)])
        if mails:
            rpc("mail.mail", "unlink", mails)
        rpc("helpdesk.ticket", "unlink", tickets)
        print(f"Puliti {len(tickets)} ticket del video precedente")
    partners = rpc.search("res.partner", [("name", "=", CLIENTE)])
    if not partners:
        return
    orders = rpc.search("sale.order", [("partner_id", "in", partners)])
    projects = rpc.search("project.project", [("partner_id", "in", partners)],
                          context={"active_test": False})
    if orders:
        projects += rpc.search("project.project", [("sale_order_id", "in", orders)],
                               context={"active_test": False})
    projects = sorted(set(projects))
    if projects:
        slots = rpc.search("lab.planning.slot", [("project_id", "in", projects)])
        if slots:
            rpc("lab.planning.slot", "write", slots, {"timesheet_id": False, "state": "cancel"})
            rpc("lab.planning.slot", "unlink", slots)
        lines = rpc.search("account.analytic.line", [("project_id", "in", projects)])
        if lines:
            rpc("account.analytic.line", "unlink", lines)
        tasks = rpc.search("project.task", [("project_id", "in", projects)],
                           context={"active_test": False})
        if tasks:
            rpc("project.task", "unlink", tasks)
        rpc("project.project", "unlink", projects)
    if orders:
        rpc("sale.order", "action_cancel", orders, context={"disable_cancel_warning": True})
        rpc("sale.order", "unlink", orders)
    rpc("res.partner", "unlink", partners)
    print(f"Puliti i dati del video precedente ({len(orders)} ordini, {len(projects)} progetti)")


# ---------------------------------------------------------------- regia nel browser
OVERLAY_JS = r"""
(() => {
  if (window.__labOverlay) return; window.__labOverlay = true;
  const mk = () => {
    if (!document.body || document.getElementById('lab-cursor')) return;
    const st = document.createElement('style');
    st.textContent = `
      #lab-cursor{position:fixed;z-index:2147483647;width:22px;height:22px;margin:-11px 0 0 -11px;
        border-radius:50%;background:rgba(255,196,0,.55);border:2px solid #b07d00;pointer-events:none;
        transition:transform .12s;left:-50px;top:-50px}
      #lab-cursor.down{transform:scale(.6);background:rgba(255,120,0,.8)}
      #lab-caption{position:fixed;z-index:2147483646;left:50%;bottom:22px;transform:translateX(-50%);
        max-width:1080px;background:rgba(20,24,33,.88);color:#fff;font:500 21px/1.35 'Segoe UI',Arial,sans-serif;
        padding:12px 22px;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.35);pointer-events:none;
        text-align:center;display:none}
      #lab-role{position:fixed;z-index:2147483646;right:14px;top:54px;background:#714b67;color:#fff;
        font:600 15px 'Segoe UI',Arial,sans-serif;padding:6px 14px;border-radius:16px;pointer-events:none;
        box-shadow:0 3px 10px rgba(0,0,0,.25);display:none}
      #lab-card{position:fixed;z-index:2147483645;inset:0;display:none;align-items:center;justify-content:center;
        flex-direction:column;background:linear-gradient(135deg,#2b1f33,#714b67);color:#fff;
        font-family:'Segoe UI',Arial,sans-serif;text-align:center;padding:40px}
      #lab-card .n{font-size:22px;opacity:.8;letter-spacing:.08em;text-transform:uppercase}
      #lab-card .t{font-size:46px;font-weight:700;margin:10px 0 14px}
      #lab-card .s{font-size:23px;opacity:.92;max-width:900px;line-height:1.4}
      .lab-hl{outline:3px solid #ffb400 !important;outline-offset:3px;border-radius:4px;
        transition:outline .2s}`;
    document.head.appendChild(st);
    for (const id of ['lab-cursor','lab-caption','lab-role','lab-card']) {
      const d = document.createElement('div'); d.id = id; document.body.appendChild(d);
    }
    document.getElementById('lab-card').innerHTML = '<div class="n"></div><div class="t"></div><div class="s"></div>';
    const s = window.__labState || {};
    if (s.caption) window.__labCaption(s.caption);
    if (s.role) window.__labRole(s.role);
  };
  window.__labState = JSON.parse(sessionStorage.getItem('labState') || '{}');
  const save = () => sessionStorage.setItem('labState', JSON.stringify(window.__labState));
  window.__labCaption = (t) => { window.__labState.caption = t; save();
    const c = document.getElementById('lab-caption'); if (!c) return;
    c.innerHTML = t || ''; c.style.display = t ? 'block' : 'none'; };
  window.__labRole = (t) => { window.__labState.role = t; save();
    const c = document.getElementById('lab-role'); if (!c) return;
    c.textContent = t || ''; c.style.display = t ? 'block' : 'none'; };
  window.__labCard = (n, t, s) => { const c = document.getElementById('lab-card'); if (!c) return;
    if (!t) { c.style.display = 'none'; return; }
    c.querySelector('.n').textContent = n; c.querySelector('.t').textContent = t;
    c.querySelector('.s').innerHTML = s || ''; c.style.display = 'flex'; };
  document.addEventListener('mousemove', e => { const c = document.getElementById('lab-cursor');
    if (c) { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; } }, true);
  document.addEventListener('mousedown', () => document.getElementById('lab-cursor')?.classList.add('down'), true);
  document.addEventListener('mouseup', () => document.getElementById('lab-cursor')?.classList.remove('down'), true);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mk); else mk();
  new MutationObserver(mk).observe(document.documentElement, {childList: true, subtree: false});
})();
"""


class Regia:
    def __init__(self, browser, opts, t0):
        self.browser = browser
        self.opts = opts
        self.context = None
        self.page = None
        self.frames = []         # (file jpg, istante) catturati da Chrome
        self.cdp = None
        self._nuovo_contesto()
        self.t0 = t0
        self.capitoli = []
        self.shot = 0
        self.mouse = (W / 2, H / 2)

    # -- tempi
    def pausa(self, sec):
        self.page.wait_for_timeout(int(sec * (0.15 if PROVA else 1) * 1000))

    def foto(self, nome):
        if PROVA:
            self.shot += 1
            self.page.screenshot(path=str(WORK / f"prova_{self.shot:02d}_{nome}.png"))

    # -- sovrimpressioni
    def dici(self, testo, sec=None):
        self.page.evaluate("t => window.__labCaption && window.__labCaption(t)", testo)
        plain = testo.replace("<b>", "").replace("</b>", "")
        self.pausa(sec if sec is not None else max(3.0, len(plain) / 14.0))

    def ruolo(self, testo):
        self.page.evaluate("t => window.__labRole && window.__labRole(t)", testo)

    def capitolo(self, numero, titolo, sottotitolo, ruolo=None):
        self.capitoli.append({"n": numero, "titolo": titolo, "t": time.monotonic()})
        self.page.evaluate("t => window.__labCaption && window.__labCaption(t)", "")
        self.page.evaluate("([n,t,s]) => window.__labCard(n,t,s)",
                           [f"Capitolo {numero}" if numero else "", titolo, sottotitolo])
        self.pausa(4.5)
        self.foto(f"cap{numero}")
        self.page.evaluate("() => window.__labCard('', '', '')")
        if ruolo is not None:
            self.ruolo(ruolo)

    # -- navigazione
    def pronto(self):
        self.page.wait_for_selector(".o_main_navbar")
        self.page.wait_for_selector(".o_action_manager > *")
        self.page.wait_for_function("() => !document.querySelector('.o_blockUI')")
        self.page.wait_for_timeout(900)

    def vai(self, path):
        self.page.goto(URL + path, wait_until="domcontentloaded")
        self.pronto()

    def _nuovo_contesto(self):
        """Ogni utente ha un profilo browser separato (una sessione lunga fa cadere Chrome)."""
        self.chiudi()
        self.context = self.browser.new_context(**self.opts)
        self.context.add_init_script(OVERLAY_JS)
        self.context.set_default_timeout(120000)
        self.page = self.context.new_page()
        if not PROVA:
            # cattura dei fotogrammi direttamente da Chrome (screencast DevTools):
            # non serve il ffmpeg di Playwright, il video lo monta il ffmpeg del PC
            self.cdp = self.context.new_cdp_session(self.page)
            self.cdp.on("Page.screencastFrame", self._fotogramma)
            self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 85,
                                                   "maxWidth": W, "maxHeight": H})

    def _fotogramma(self, params):
        path = FRAMES / f"{len(self.frames):06d}.jpg"
        path.write_bytes(base64.b64decode(params["data"]))
        self.frames.append((path, time.monotonic()))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:  # noqa: BLE001  (pagina gia' chiusa)
            pass

    def chiudi(self):
        if self.context:
            if self.cdp:
                try:
                    self.cdp.send("Page.stopScreencast")
                except Exception:  # noqa: BLE001
                    pass
                self.cdp = None
            self.context.close()
            self.context = None

    def nuova_pagina(self):
        self._nuovo_contesto()

    def login(self, utente, ruolo):
        self.nuova_pagina()
        self.page.goto(URL + "/web/session/logout", wait_until="domcontentloaded")
        self.page.goto(URL + "/web/login", wait_until="domcontentloaded")
        self.ruolo(ruolo)
        self.dici(f"Accesso come <b>{utente}</b> ({ruolo})", 1.5)
        # con il Sito web installato la pagina di login ha anche altri pulsanti (es. ricerca):
        # si usa quello del modulo di accesso
        form = self.page.locator("form.oe_login_form")
        self.scrivi(form.locator("input[name=login]"), utente)
        form.locator("input[name=password]").fill(PWD_USERS)
        self.clic(form.locator("button[type=submit]"))
        self.pronto()

    # -- mouse e tastiera visibili
    def _muovi(self, loc):
        box = None
        for _tentativo in range(20):  # l'elemento puo' essere ridisegnato da Odoo: riprova
            try:
                loc.first.wait_for(state="visible")
                loc.first.scroll_into_view_if_needed(timeout=5000)
                box = loc.first.bounding_box(timeout=5000)
            except Exception:  # noqa: BLE001
                box = None
            if box:
                break
            self.page.wait_for_timeout(300)
        if not box:
            raise RuntimeError(f"Elemento non visibile: {loc}")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.move(x, y, steps=1 if PROVA else 18)
        self.mouse = (x, y)
        self.pausa(0.35)

    def clic(self, loc, pausa=0.8):
        loc = loc.first
        self._muovi(loc)
        loc.click()
        self.pausa(pausa)

    def evidenzia(self, loc, sec=2.5):
        loc = loc.first
        self._muovi(loc)
        loc.evaluate("e => e.classList.add('lab-hl')")
        self.pausa(sec)
        loc.evaluate("e => e.classList.remove('lab-hl')")

    def scrivi(self, loc, testo):
        loc = loc.first
        self._muovi(loc)
        loc.click()
        loc.press_sequentially(testo, delay=5 if PROVA else 70)
        self.pausa(0.4)

    def scegli(self, campo, testo, voce=None):
        """Campo many2one: scrive e sceglie la voce dal menu a tendina."""
        inp = self.page.locator(f"div[name={campo}] input").first
        inp.fill("")
        self.scrivi(inp, testo)
        item = self.page.locator(".o-autocomplete--dropdown-item", has_text=voce or testo)
        item.first.wait_for(state="visible")
        self.page.wait_for_timeout(700)  # attende la fine della ricerca
        self.pausa(0.3)
        self.clic(item, 1.0)

    def bottone(self, nome, pausa=1.5):
        btn = self.page.locator(f"button[name={nome}]:visible")
        self.clic(btn, pausa)

    def salva(self):
        self.clic(self.page.locator(".o_form_button_save:visible"), 1.5)

    def scheda(self, testo):
        self.clic(self.page.locator(".o_notebook .nav-link", has_text=testo), 1.2)


# ---------------------------------------------------------------- copione
def copione(r, rpc):
    oggi = date.today()

    # Copertina
    r.page.goto(URL + "/web/login", wait_until="domcontentloaded")
    r.capitolo(0, "Flusso Operativo Software House",
               "Odoo 18 Community · dalla vendita al margine di commessa<br>"
               "Dimostrazione con gli utenti dei cinque ruoli")

    # 1. Commerciale: ordine -> commessa
    r.capitolo(1, "Il Commerciale vende un pacchetto di ore",
               "Preventivo, conferma e creazione automatica della commessa", "")
    r.login("giuseppe", "Commerciale")
    r.vai("/odoo/action-sale.action_quotations_with_onboarding/new")
    r.dici("Il Commerciale prepara un preventivo per un nuovo cliente.")
    r.scegli("partner_id", CLIENTE, f'Crea "{CLIENTE}"')
    r.pausa(1.0)
    r.clic(r.page.locator(".o_field_x2many_list_row_add a:has-text('Aggiungi prodotto')"), 1.0)
    r.page.keyboard.type("Pacchetto Monte Ore", delay=5 if PROVA else 70)
    item = r.page.locator(".o-autocomplete--dropdown-item", has_text="Pacchetto Monte Ore (50h)")
    item.first.wait_for(state="visible")
    r.pausa(0.8)
    r.clic(item, 1.5)
    r.dici("Prodotto <b>Pacchetto Monte Ore (50h)</b>: 1 unità vale 50 ore "
           "(campo <i>Ore per unità</i> del prodotto).")
    r.foto("preventivo")
    r.dici("Alla conferma Odoo crea la commessa riservata agli invitati, con le ore vendute "
           "e i task già stimati.", 4)
    r.bottone("action_confirm", 3.0)
    r.foto("ordine_confermato")
    r.dici("Ordine confermato: la commessa è pronta per il Project Manager.", 3.5)

    order_id = rpc.search("sale.order", [("partner_id.name", "=", CLIENTE)],
                          order="id desc", limit=1)[0]
    order_name = rpc("sale.order", "read", [order_id], ["name"])[0]["name"]
    project_id = rpc.search("project.project", [("sale_order_id", "=", order_id)], limit=1)[0]
    project = rpc("project.project", "read", [project_id], ["display_name"])[0]
    tasks = {t["name"]: t["id"] for t in rpc("project.task", "search_read",
                                               [("project_id", "=", project_id)], ["name"])}
    task_analisi = next(i for n, i in tasks.items() if n.startswith("Analisi"))

    # 2. PM: la commessa nata dall'ordine
    r.capitolo(2, "Il Project Manager trova la commessa pronta",
               "Monte ore venduto, tipo contratto e 4 task stimati in automatico", "")
    r.login("marco", "Project Manager")
    r.vai(f"/odoo/action-project.open_view_project_all/{project_id}")
    r.dici("La scheda della commessa mostra il gruppo <b>Monte ore</b>: 50 ore vendute, "
           "stimate e consuntivate.")
    r.evidenzia(r.page.locator("div[name=lab_sold_hours]").locator(".."), 2.0)
    r.evidenzia(r.page.locator("div[name=lab_contract_type]"), 2.5)
    r.dici("Il <b>tipo contratto</b> deriva dal prodotto venduto: qui è a corpo / monte ore "
           "prepagato.")
    r.foto("commessa")
    r.vai(f"/odoo/project/{project_id}/tasks")
    r.dici("I task sono già creati e stimati: Analisi 15%, Project Management 10%, "
           "Sviluppo 60%, Test 15% delle ore vendute.", 6)
    r.foto("task")

    # 3. PM: pianificazione 80/20
    r.capitolo(3, "Pianificazione con la regola 80/20",
               "Al massimo 32 ore a settimana per persona × fattore parallelo", "Project Manager")
    r.vai("/odoo/action-lab_workflow_custom.action_all_slots")
    r.dici("Nel calendario del team ci sono i turni della settimana. Niccolò ha già 32 ore: "
           "il suo limite.", 5)
    r.foto("calendario")
    r.vai("/odoo/action-lab_workflow_custom.action_all_slots/new")
    r.dici("Proviamo ad assegnargli altre ore questa settimana…", 2.5)
    r.scegli("employee_id", "Niccol", "Niccolò")
    r.scegli("project_id", "Gestionale sinistri")
    r.salva()
    dialog = r.page.locator(".modal-dialog:visible")
    dialog.first.wait_for(state="visible")
    r.dici("Odoo blocca il turno: oltre il limite della regola 80/20. Il 20% del tempo resta "
           "per formazione, supporto e imprevisti.", 6)
    r.foto("blocco_8020")
    r.clic(dialog.locator(".modal-footer button").first, 1.0)
    r.clic(r.page.locator(".o_form_button_cancel:visible"), 1.5)

    r.vai("/odoo/action-lab_workflow_custom.action_all_slots/new")
    r.dici("Ora un turno per Giulia, analista, sul task di Analisi della nuova commessa.", 3)
    r.scegli("employee_id", "Giulia")
    r.scegli("project_id", order_name, project["display_name"][:20])
    r.scegli("task_id", "Analisi")
    hours = r.page.locator("div[name=allocated_hours] input").first
    hours.fill("")
    r.scrivi(hours, "6")
    r.page.keyboard.press("Tab")
    r.salva()
    r.dici("Il riquadro della settimana mostra ore già pianificate, limite reale e fattore "
           "parallelo della persona.", 5)
    r.foto("turno_salvato")
    r.dici("Il PM pubblica il turno: Giulia riceve la notifica.", 3)
    r.bottone("action_publish", 2.0)
    slot_id = rpc.search("lab.planning.slot", [("project_id", "=", project_id)], limit=1)[0]

    # 4. Analista: conferma -> foglio ore
    r.capitolo(4, "L'analista conferma il turno",
               "La conferma crea da sola la riga del foglio ore", "")
    r.login("giulia", "Analista funzionale")
    r.vai("/odoo/action-lab_workflow_custom.action_my_slots")
    r.dici("In <b>I miei turni</b> Giulia vede solo i turni pubblicati per lei.", 4)
    r.foto("miei_turni")
    r.vai(f"/odoo/action-lab_workflow_custom.action_my_slots/{slot_id}")
    r.dici("A fine giornata corregge le ore effettive (oggi 7 invece di 6) e conferma.", 3.5)
    eff = r.page.locator("div[name=confirmed_hours] input").first
    eff.fill("")
    r.scrivi(eff, "7")
    r.page.keyboard.press("Tab")
    r.bottone("action_confirm", 2.5)
    r.dici("Turno confermato: Odoo ha creato la riga del <b>foglio ore</b> con task e commessa.", 4)
    r.foto("turno_confermato")
    r.clic(r.page.locator("button[name=action_open_timesheet]"), 2.0)
    r.pronto()
    r.dici("Ecco la riga del foglio ore: nessuna doppia registrazione.", 4)
    r.foto("foglio_ore")

    # 5. PM: alert monte ore
    r.capitolo(5, "Alert sul monte ore",
               "Avviso giallo al 75% e rosso al 90%, sul task e sulla commessa", "")
    r.login("marco", "Project Manager")
    r.vai(f"/odoo/project/{project_id}/tasks/{task_analisi}")
    r.dici("Il task di Analisi aveva 7,5 ore stimate: con 7 ore consuntivate è oltre il 90%.", 4)
    r.evidenzia(r.page.locator(".alert-danger:visible"), 3.5)
    r.foto("alert_task")
    r.vai("/odoo/action-project.open_view_project_all")
    r.dici("Lo stesso controllo vale per la commessa: qui le etichette gialle e rosse delle "
           "commesse demo vicine all'esaurimento.", 5.5)
    r.foto("kanban_progetti")

    # 6. Ore parallele
    r.capitolo(6, "Lavoro in parallelo",
               "Il costo della giornata non raddoppia; le ore extra le approva il PM",
               "Project Manager")
    r.vai("/odoo/action-lab_workflow_custom.action_parallel_to_approve")
    r.clic(r.page.locator(".o_group_header", has_text="Carlo"), 1.5)
    r.dici("Carlo ha segnato più ore della sua giornata su più commesse: le ore restano "
           "tutte, il costo si divide.", 5)
    r.evidenzia(r.page.locator("button[name=action_lab_approve_parallel]:visible"), 1.5)
    r.dici("Sui contratti T&amp;M queste ore entrano in fattura solo dopo l'<b>Approva</b> "
           "del PM.", 4.5)
    r.foto("parallele")

    # 7. Economia della commessa
    bianchi = rpc.search("project.project", [("partner_id.name", "ilike", "Bianchi Logistica")],
                         limit=1)[0]
    r.capitolo(7, "Costi, ricavi e margine della commessa",
               "Consulenti esterni, pass-through al cliente e pacchetti tracciati per task",
               "Project Manager")
    r.vai(f"/odoo/action-project.open_view_project_all/{bianchi}")
    r.scheda("Costi, ricavi e margine")
    r.evidenzia(r.page.locator("div[name=lab_margin]"), 0.5)
    r.dici("Commessa T&amp;M Bianchi: ricavi, costi per natura e margine, dagli stessi numeri "
           "del report margini.", 5)
    r.foto("economia")
    r.dici("La fattura del consulente esterno è stata ribaltata al cliente con il 15% di "
           "ricarico; il costo AI viene dalla ripartizione mensile.", 6)
    btn = r.page.locator("button[name=action_lab_open_consumption]:visible")
    if btn.count():
        r.clic(btn, 2.0)
        r.pronto()
        r.clic(r.page.locator(".o_group_header").first, 1.5)
        r.dici("<b>Ore per task</b>: ogni ora scalata dal pacchetto dice su quale attività è "
               "stata spesa.", 5)
        r.foto("ore_per_task")
    r.vai("/odoo/action-lab_workflow_custom.action_margin_report")
    r.dici("Il report <b>Margini per commessa</b> confronta tutte le commesse: venduto, "
           "ribaltato, costi e margine.", 6)
    r.foto("margini")

    # 8. Amministrazione: costi AI e chiusura mese
    r.capitolo(8, "Costi AI, consulenti e chiusura del mese",
               "Licenze e consumi AI ripartiti sulle commesse, tariffe dei consulenti, chiusura del mese",
               "")
    r.login("luana", "Amministrazione")
    r.vai("/odoo/action-lab_workflow_custom.action_cost_periods")
    r.dici("Ogni mese ha la sua ripartizione: quello scorso è chiuso, quello in corso si "
           "ricalcola ogni notte.", 5)
    r.foto("mesi")
    r.clic(r.page.locator(".o_data_row").nth(1), 2.0)
    r.pronto()
    r.dici("Licenze divise sulle ore delle persone, consumi API dedicati alla commessa, "
           "il resto nei costi generali.", 6)
    r.foto("mese_chiuso")
    r.vai("/odoo/action-lab_workflow_custom.action_ai_usage")
    r.dici("<b>Consumi AI</b>: a mano, da CSV o dal connettore Anthropic (spento nell'ambiente "
           "demo). Le corrispondenze decidono dove va ogni importo.", 6.5)
    r.foto("consumi")
    r.vai("/odoo/action-lab_workflow_custom.action_ai_licenses")
    r.dici("<b>Licenze AI</b> assegnate alle persone: il costo mensile si divide sulle "
           "commesse in base alle ore, o come quota di governance per i PM.", 6.5)
    r.foto("licenze")
    carlo = rpc.search("hr.employee", [("name", "ilike", "Carlo"),
                                       ("lab_resource_type", "=", "external")], limit=1)
    if carlo:
        r.vai(f"/odoo/action-hr.open_view_employee_list_my/{carlo[0]}")
        r.scheda("Costi e AI")
        r.page.evaluate("() => document.querySelector('.o_notebook')"
                        ".scrollIntoView({block: 'start', behavior: 'smooth'})")
        r.pausa(1.0)
        r.evidenzia(r.page.locator("div[name=lab_vendor_id]"), 0.5)
        r.dici("Scheda persona di Carlo, <b>consulente esterno</b>: l'Amministrazione indica il "
               "fornitore che fattura e la tariffa concordata.", 6)
        r.evidenzia(r.page.locator("div[name=lab_external_rate]"), 0.5)
        r.dici("Finché la fattura non arriva, la commessa vede il costo <b>maturato</b>: ore × "
               "tariffa.", 5)
        r.foto("consulente")

    # 9. Ticket di assistenza: il cliente scrive dal sito, il Supporto lo prende in carico
    r.capitolo(9, "Ticket di assistenza",
               "Il cliente apre la richiesta dal sito; il ticket va da solo sulla commessa AMS",
               "Cliente (sito pubblico)")
    r.nuova_pagina()
    r.ruolo("Cliente (sito pubblico)")
    r.page.goto(URL + "/assistenza", wait_until="domcontentloaded")
    r.page.wait_for_selector("#lab_helpdesk_form")
    r.pausa(1.0)
    r.dici("Il cliente di un canone AMS apre la pagina pubblica <b>Assistenza</b>: "
           "non serve un account.", 4)
    form = r.page.locator("#lab_helpdesk_form")
    r.scrivi(form.locator("input[name=partner_name]"), "Mario Verdi")
    r.scrivi(form.locator("input[name=partner_email]"), EMAIL_AMS)
    r.scrivi(form.locator("input[name=name]"), TICKET_VIDEO)
    form.locator("select[name=type_id]").select_option(label="Malfunzionamento")
    form.locator("select[name=priority]").select_option(value="2")
    # Descrizione con l'editor del modulo (grassetto ed elenco puntato, come in una email)
    editor = form.locator(".lab_rich_editor")
    editor.wait_for(timeout=60000)
    r.scrivi(editor, "Dalle 9 la stampa delle bolle ")
    r.page.keyboard.press("Control+B")
    r.page.keyboard.type("va in errore", delay=5 if PROVA else 70)
    r.page.keyboard.press("Control+B")
    r.page.keyboard.type(". Passaggi:", delay=5 if PROVA else 70)
    r.page.keyboard.press("Enter")
    r.clic(form.locator("button[data-cmd=insertUnorderedList]"), 0.4)
    r.page.keyboard.type("apro i DDT del giorno", delay=5 if PROVA else 70)
    r.page.keyboard.press("Enter")
    r.page.keyboard.type("premo Stampa", delay=5 if PROVA else 70)
    r.pausa(0.5)
    r.foto("modulo_ticket")
    r.dici("La descrizione si scrive come una email: grassetto, elenchi, link e "
           "schermate incollate con Ctrl+V.", 4.5)
    r.dici("Tipo, urgenza e allegati. Il modulo è protetto contro lo spam.", 3)
    r.clic(form.locator(".s_website_form_send"), 1.0)
    r.page.wait_for_url("**/assistenza-grazie", timeout=60000)
    r.pausa(1.0)
    r.dici("Richiesta inviata: arriva un'email con il numero del ticket e il pulsante "
           "<b>Segui il ticket</b>.", 5)
    r.foto("ticket_inviato")
    ticket_id = rpc.search("helpdesk.ticket", [("name", "=", TICKET_VIDEO)],
                           order="id desc", limit=1)[0]

    r.login("nicola", "Supporto")
    r.vai(f"/odoo/action-helpdesk_mgmt.helpdesk_ticket_action/{ticket_id}")
    r.dici("Per il Supporto il ticket è già pronto: Odoo ha riconosciuto il cliente "
           "dall'email…", 4)
    r.evidenzia(r.page.locator("div[name=partner_id]"), 1.5)
    r.evidenzia(r.page.locator("div[name=project_id]:visible"), 1.5)
    r.dici("…e l'ha collegato alla sua <b>commessa a canone AMS</b>: le ore segnate sul ticket "
           "scalano il monte ore del mese.", 5.5)
    r.evidenzia(r.page.locator("div[name=lab_consumption_pct]"), 2.5)
    r.foto("ticket_backend")
    r.dici("Urgenza alta su un canone AMS: <b>SLA</b> di presa in carico entro 8 ore "
           "lavorative.", 4.5)
    r.bottone("assign_to_me", 1.5)
    r.clic(r.page.locator(".o_statusbar_status button", has_text="In corso"), 2.0)
    r.dici("Nicola lo prende in carico: il cliente riceve l'email «Stiamo lavorando alla tua "
           "richiesta» e lo SLA risulta rispettato.", 5.5)
    r.foto("ticket_in_corso")
    r.vai("/odoo/action-helpdesk_mgmt.helpdesk_ticket_action?view_type=kanban")
    r.dici("Per stadio: ticket nuovi, in corso, in attesa del cliente e chiusi con valutazione; "
           "l'urgente con lo SLA scaduto va gestito subito.", 6)
    r.foto("ticket_lista")

    # Chiusura
    r.ruolo("")
    r.page.evaluate("() => window.__labCaption('')")
    r.capitolo(10, "Riepilogo",
               "Vendita → commessa → pianificazione 80/20 → foglio ore → alert → costi e "
               "margini → ticket di assistenza.<br>Documentazione completa nella scheda dell'app.")
    r.pausa(1.5)


# ---------------------------------------------------------------- pagina dell'app
def aggiorna_capitoli_index(capitoli):
    """Scrive l'elenco dei capitoli (con i minuti) nella pagina dell'app, tra i segnaposto."""
    index = DESC / "index.html"
    html = index.read_text(encoding="utf-8")
    start, end = "<!-- CAPITOLI_VIDEO -->", "<!-- /CAPITOLI_VIDEO -->"
    if start not in html or end not in html:
        print("Segnaposto dei capitoli non trovato in index.html: elenco non aggiornato")
        return
    voci = []
    for c in capitoli:
        if not c["n"]:
            continue
        s = c["secondi"]
        voci.append(
            f'  <li><a href="/lab_workflow_custom/static/description/video.html#t={s}" '
            f'target="_blank">{s // 60}:{s % 60:02d}</a> – {c["titolo"]}</li>')
    blocco = (f'{start}\n<p style="margin-bottom:4px"><b>Capitoli</b> (il minuto apre il video '
              f'da quel punto)</p>\n<ol style="font-size:14px;columns:2;column-gap:32px">\n'
              + "\n".join(voci) + f"\n</ol>\n{end}")
    a, b = html.index(start), html.index(end) + len(end)
    index.write_text(html[:a] + blocco + html[b:], encoding="utf-8")
    print("Capitoli aggiornati in index.html")


# ---------------------------------------------------------------- main
def main():
    if "--solo-capitoli" in sys.argv:
        aggiorna_capitoli_index(json.loads((DESC / "video_capitoli.json").read_text("utf-8")))
        return
    shutil.rmtree(WORK, ignore_errors=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    rpc = Rpc()
    pulisci_dati_video(rpc)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        opts = {"viewport": {"width": W, "height": H}, "locale": "it-IT",
                "device_scale_factor": 1}
        t0 = time.monotonic()
        r = Regia(browser, opts, t0)
        try:
            copione(r, rpc)
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                r.page.screenshot(path=str(WORK / "errore.png"), timeout=10000)
                print("Errore: schermata salvata in", WORK / "errore.png")
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            r.chiudi()
            browser.close()
    t_start = r.frames[0][1] if r.frames else r.t0
    for c in r.capitoli:
        c["secondi"] = max(0, round(c.pop("t") - t_start))
    for c in r.capitoli:
        print(f"{c['secondi'] // 60}:{c['secondi'] % 60:02d}  {c['n']}. {c['titolo']}")
    if PROVA:
        print("Prova completata: schermate in", WORK)
        return
    (DESC / "video_capitoli.json").write_text(
        json.dumps(r.capitoli, ensure_ascii=False, indent=1), encoding="utf-8")
    aggiorna_capitoli_index(r.capitoli)
    # montaggio: ogni fotogramma resta a schermo fino al successivo (frequenza variabile)
    mp4 = DESC / "demo_flusso_operativo.mp4"
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    elenco = WORK / "fotogrammi.txt"
    righe = []
    for i, (path, t) in enumerate(r.frames):
        fine = r.frames[i + 1][1] if i + 1 < len(r.frames) else t + 2.0
        righe += [f"file '{path.as_posix()}'", f"duration {max(fine - t, 0.001):.3f}"]
    righe.append(f"file '{r.frames[-1][0].as_posix()}'")
    elenco.write_text("\n".join(righe) + "\n", encoding="utf-8")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(elenco), "-vf",
                    f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                    f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=white,fps=25,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "28",
                    "-movflags", "+faststart", "-an", str(mp4)], check=True)
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "2", "-i", str(mp4),
                    "-frames:v", "1", str(DESC / "video_copertina.png")], check=True)
    print("Video:", mp4, f"({mp4.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
