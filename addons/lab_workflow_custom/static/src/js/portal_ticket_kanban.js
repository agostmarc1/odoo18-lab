/** @odoo-module **/
/**
 * Portale clienti: la bacheca Kanban dei ticket (/my/tickets/kanban) si aggiorna da sola.
 *
 * - Tempo reale: Odoo manda l'avviso "lab_ticket_update" sul canale personale dell'utente
 *   (solo agli utenti dell'azienda del ticket, vedi models/helpdesk_ticket.py _lab_notify_portal);
 *   l'avviso contiene solo i numeri dei ticket, i dati si rileggono con i permessi del cliente.
 * - Ripiego: ricarica comunque ogni 60 secondi (es. firewall che blocca i websocket).
 */
import publicWidget from "@web/legacy/js/public/public_widget";

const POLL_MS = 60000;

publicWidget.registry.LabTicketKanban = publicWidget.Widget.extend({
    selector: "#lab_ticket_kanban",

    start() {
        this._refresh = this._refresh.bind(this);
        this._onUpdate = this._onUpdate.bind(this);
        try {
            this.call("bus_service", "subscribe", "lab_ticket_update", this._onUpdate);
            this.call("bus_service", "start");
        } catch {
            // senza bus resta l'aggiornamento periodico
        }
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
