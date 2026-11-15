/** @odoo-module **/
/**
 * Portale clienti: la bacheca Kanban dei ticket (/my/tickets/kanban) si aggiorna da sola.
 *
 * - Tempo reale: Odoo manda l'avviso "lab_ticket_update" sul canale personale dell'utente
 *   (solo agli utenti dell'azienda del ticket, vedi models/helpdesk_ticket.py _lab_notify_portal);
 *   l'avviso contiene solo i numeri dei ticket, i dati si rileggono con i permessi del cliente.
 * - Ripiego: ricarica comunque ogni 60 secondi (es. firewall che blocca i websocket).
 * - Colonne riducibili: clic sul titolo. La scelta resta salvata in questo browser
 *   (localStorage); senza scelta, "Risolto" parte ridotta come le colonne chiuse di Odoo.
 */
import publicWidget from "@web/legacy/js/public/public_widget";

const POLL_MS = 60000;
const FOLD_KEY = "lab_ticket_kanban_folded";

function readFolds() {
    try {
        return JSON.parse(window.localStorage.getItem(FOLD_KEY) || "{}") || {};
    } catch {
        return {};
    }
}

function saveFolds(folds) {
    try {
        window.localStorage.setItem(FOLD_KEY, JSON.stringify(folds));
    } catch {
        // navigazione privata: la scelta vale solo fino al prossimo caricamento
    }
}

publicWidget.registry.LabTicketKanban = publicWidget.Widget.extend({
    selector: "#lab_ticket_kanban",
    events: {
        "click .lab_kanban_toggle": "_onToggle",
    },

    start() {
        this._refresh = this._refresh.bind(this);
        this._onUpdate = this._onUpdate.bind(this);
        try {
            this.call("bus_service", "subscribe", "lab_ticket_update", this._onUpdate);
            this.call("bus_service", "start");
        } catch {
            // senza bus resta l'aggiornamento periodico
        }
        this._folds = readFolds();
        this._applyFolds();
        this._timer = setInterval(this._refresh, POLL_MS);
        return this._super(...arguments);
    },

    destroy() {
        clearInterval(this._timer);
        try {
            this.call("bus_service", "unsubscribe", "lab_ticket_update", this._onUpdate);
        } catch {
            // nulla
        }
        this._super(...arguments);
    },

    _onToggle(ev) {
        const column = ev.currentTarget.closest(".lab_kanban_column");
        const folded = !column.classList.contains("lab_kanban_folded");
        this._folds[column.dataset.column] = folded;
        saveFolds(this._folds);
        this._applyFolds();
    },

    _applyFolds() {
        for (const column of this.el.querySelectorAll(".lab_kanban_column")) {
            const key = column.dataset.column;
            if (key in this._folds) {
                column.classList.toggle("lab_kanban_folded", this._folds[key]);
            }
            const folded = column.classList.contains("lab_kanban_folded");
            column.querySelector(".lab_kanban_toggle")?.setAttribute("aria-expanded", String(!folded));
        }
    },

    _onUpdate(payload) {
        this._changed = new Set((payload && payload.ticket_ids) || []);
        this._refresh();
    },

    async _refresh() {
        if (this._loading) {
            return;
        }
        this._loading = true;
        try {
            const scope = this.el.dataset.scope || "company";
            const response = await fetch(`/my/tickets/kanban?scope=${encodeURIComponent(scope)}&fragment=1`,
                { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } });
            if (!response.ok) {
                return;
            }
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, "text/html");
            const board = doc.querySelector(".lab_kanban_board");
            if (!board) {
                return; // es. sessione scaduta: la pagina di login non ha la bacheca
            }
            this.el.replaceChildren(board);
            this._applyFolds();
            for (const id of this._changed || []) {
                const card = this.el.querySelector(`[data-ticket-id="${Number(id)}"]`);
                card?.classList.add("lab_kanban_card_changed");
            }
            this._changed = null;
        } finally {
            this._loading = false;
        }
    },
});

export default publicWidget.registry.LabTicketKanban;
