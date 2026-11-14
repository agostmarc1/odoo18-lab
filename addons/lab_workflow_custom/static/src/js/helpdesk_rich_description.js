/** @odoo-module **/
/**
 * Modulo pubblico "Apri un ticket" (/assistenza): il campo Descrizione diventa un piccolo editor
 * come quello di un programma di posta (grassetto, corsivo, sottolineato, elenchi, link, immagini).
 *
 * - La barra è sempre visibile (il cliente non deve sapere che "basta selezionare il testo").
 * - Le immagini si aggiungono con il pulsante, incollandole (Ctrl+V) o trascinandole: restano
 *   dentro il testo (data URI ridimensionate a max 1600 px); al salvataggio Odoo le trasforma in
 *   allegati del ticket (models/helpdesk_ticket.py, _lab_store_inline_images).
 * - Il testo HTML va nella textarea originale (nascosta) con il campo lab_rich=1: il server lo
 *   ripulisce (niente script, niente link javascript:). Senza JavaScript resta la textarea normale.
 */
import publicWidget from "@web/legacy/js/public/public_widget";

const MAX_IMAGES = 10;
const MAX_SIDE = 1600;
const MAX_FILE_MB = 15;

const BUTTONS = [
    { cmd: "bold", icon: "fa-bold", title: "Grassetto (Ctrl+B)" },
    { cmd: "italic", icon: "fa-italic", title: "Corsivo (Ctrl+I)" },
    { cmd: "underline", icon: "fa-underline", title: "Sottolineato (Ctrl+U)" },
    { sep: true },
    { cmd: "insertUnorderedList", icon: "fa-list-ul", title: "Elenco puntato" },
    { cmd: "insertOrderedList", icon: "fa-list-ol", title: "Elenco numerato" },
    { sep: true },
    { cmd: "link", icon: "fa-link", title: "Inserisci un link" },
    { cmd: "unlink", icon: "fa-unlink", title: "Togli il link" },
    { cmd: "image", icon: "fa-picture-o", title: "Inserisci un'immagine (anche Ctrl+V o trascinandola)" },
    { sep: true },
    { cmd: "removeFormat", icon: "fa-eraser", title: "Togli la formattazione" },
];

function readAsDataURL(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

/** Ridimensiona le immagini grandi (le foto del telefono pesano molti MB). */
async function imageToDataURL(file) {
    const url = await readAsDataURL(file);
    if (file.type === "image/gif") {
        return url; // le GIF animate non si ridisegnano
    }
    const img = await new Promise((resolve, reject) => {
        const el = new Image();
        el.onload = () => resolve(el);
        el.onerror = reject;
        el.src = url;
    });
    const ratio = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    if (ratio === 1 && file.size < 1024 * 1024) {
        return url;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.naturalWidth * ratio);
    canvas.height = Math.round(img.naturalHeight * ratio);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    return file.type === "image/png"
        ? canvas.toDataURL("image/png")
        : canvas.toDataURL("image/jpeg", 0.85);
}

publicWidget.registry.LabHelpdeskRichDescription = publicWidget.Widget.extend({
    selector: "#lab_helpdesk_form",
    disabledInEditableMode: true,

    start() {
        this.textarea = this.el.querySelector("textarea[name=description]");
        if (!this.textarea) {
            return this._super(...arguments);
        }
        this._buildEditor();
        // prima del controllo del form builder (fase di cattura): copia il testo nella textarea
        this._onSendCapture = this._onSendCapture.bind(this);
        this.el.addEventListener("click", this._onSendCapture, true);
        return this._super(...arguments);
    },

    destroy() {
        this.el.removeEventListener("click", this._onSendCapture, true);
        if (this.wrapper) {
            this.wrapper.remove();
            this.fileInput.remove();
            this.textarea.classList.remove("d-none");
            this.textarea.required = true;
            this.richFlag.remove();
        }
        this._super(...arguments);
    },

    // ---------------------------------------------------------------- costruzione
    _buildEditor() {
        const ta = this.textarea;
        this.wrapper = document.createElement("div");
        this.wrapper.className = "lab_rich_wrapper";

        const toolbar = document.createElement("div");
        toolbar.className = "lab_rich_toolbar btn-toolbar border rounded-top bg-light px-1 py-1";
        toolbar.setAttribute("role", "toolbar");
        toolbar.setAttribute("aria-label", "Formattazione della descrizione");
        for (const button of BUTTONS) {
            if (button.sep) {
                const sep = document.createElement("span");
                sep.className = "lab_rich_sep border-start mx-1";
                toolbar.append(sep);
                continue;
            }
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-sm btn-light";
            btn.title = button.title;
            btn.setAttribute("aria-label", button.title);
            btn.dataset.cmd = button.cmd;
            btn.innerHTML = `<i class="fa fa-fw ${button.icon}"></i>`;
            // mousedown: non togliere il cursore dal testo
            btn.addEventListener("mousedown", (ev) => ev.preventDefault());
            btn.addEventListener("click", () => this._command(button.cmd));
            toolbar.append(btn);
        }

        this.editor = document.createElement("div");
        this.editor.className = "lab_rich_editor form-control rounded-0 rounded-bottom";
        this.editor.contentEditable = "true";
        this.editor.setAttribute("role", "textbox");
        this.editor.setAttribute("aria-multiline", "true");
        this.editor.dataset.placeholder = ta.getAttribute("placeholder") || "";
        this.editor.id = `${ta.id}_rich`;
        this.editor.innerHTML = "<p><br></p>";

        this.fileInput = document.createElement("input");
        this.fileInput.type = "file";
        this.fileInput.accept = "image/png,image/jpeg,image/gif,image/webp";
        this.fileInput.multiple = true;
        this.fileInput.className = "d-none";
        // nessun name: il form builder non lo invia come allegato
        this.fileInput.addEventListener("change", () => {
            this._insertImages([...this.fileInput.files]);
            this.fileInput.value = "";
        });

        this.hint = document.createElement("div");
        this.hint.className = "form-text";
        this.hint.textContent = "Puoi usare grassetto, elenchi e link; le schermate si incollano " +
            "direttamente con Ctrl+V.";

        this.wrapper.append(toolbar, this.editor, this.hint);
        // fuori dal form: il form builder trasforma ogni campo file in un pulsante "Aggiungi file"
        document.body.append(this.fileInput);
        ta.after(this.wrapper);
        ta.classList.add("d-none");
        ta.required = false; // il controllo lo fa _onSendCapture
        const label = this.el.querySelector(`label[for="${ta.id}"]`);
        if (label) {
            label.id = label.id || `${ta.id}_label`;
            this.editor.setAttribute("aria-labelledby", label.id);
            label.addEventListener("click", () => this.editor.focus());
        }

        this.richFlag = document.createElement("input");
        this.richFlag.type = "hidden";
        this.richFlag.name = "lab_rich";
        this.richFlag.value = "1";
        this.el.append(this.richFlag);

        document.execCommand("defaultParagraphSeparator", false, "p");
        this.editor.addEventListener("input", () => this._sync());
        this.editor.addEventListener("paste", (ev) => this._onPaste(ev));
        this.editor.addEventListener("drop", (ev) => this._onDrop(ev));
        this.editor.addEventListener("keydown", (ev) => {
            if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
                ev.preventDefault();
                this._command("link");
            }
        });
    },

    // ---------------------------------------------------------------- comandi
    _command(cmd) {
        this.editor.focus();
        if (cmd === "image") {
            this._saveRange();
            this.fileInput.click();
            return;
        }
        if (cmd === "link") {
            this._insertLink();
        } else {
            document.execCommand(cmd, false, null);
        }
        this._sync();
    },

    _insertLink() {
        const selection = window.getSelection();
        const text = selection.toString();
        let url = window.prompt("Indirizzo del link (es. www.esempio.it)", "https://");
        if (!url || url === "https://") {
            return;
        }
        url = url.trim();
        if (!/^(https?:|mailto:)/i.test(url)) {
            url = (url.includes("@") && !url.includes("/") ? "mailto:" : "https://") + url;
        }
        if (text) {
            document.execCommand("createLink", false, url);
        } else {
            const a = document.createElement("a");
            a.href = url;
            a.textContent = url.replace(/^mailto:/i, "");
            document.execCommand("insertHTML", false, a.outerHTML + "&nbsp;");
        }
    },

    _saveRange() {
        const selection = window.getSelection();
        this.savedRange = selection.rangeCount && this.editor.contains(selection.anchorNode)
            ? selection.getRangeAt(0).cloneRange() : null;
    },

    _restoreRange() {
        this.editor.focus();
        if (this.savedRange) {
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(this.savedRange);
            this.savedRange = null;
        }
    },

    async _insertImages(files) {
        const images = files.filter((f) => /^image\/(png|jpeg|gif|webp)$/.test(f.type));
        if (!images.length) {
            return;
        }
        const already = this.editor.querySelectorAll("img").length;
        if (already + images.length > MAX_IMAGES) {
            this._message(`Puoi inserire al massimo ${MAX_IMAGES} immagini nella descrizione: ` +
                "le altre aggiungile come allegati.");
            images.splice(Math.max(0, MAX_IMAGES - already));
        }
        this._restoreRange();
        for (const file of images) {
            if (file.size > MAX_FILE_MB * 1024 * 1024) {
                this._message(`L'immagine “${file.name}” è troppo grande (max ${MAX_FILE_MB} MB).`);
                continue;
            }
            const src = await imageToDataURL(file);
            const html = `<img src="${src}" class="img-fluid" alt="${file.name.replace(/"/g, "")}">`;
            document.execCommand("insertHTML", false, html);
        }
        this._sync();
    },

    _onPaste(ev) {
        const files = [...(ev.clipboardData?.files || [])];
        if (files.some((f) => f.type.startsWith("image/"))) {
            ev.preventDefault();
            this._saveRange();
            this._insertImages(files);
        }
        // testo e HTML incollati (es. da Outlook o Word): li gestisce il browser,
        // il server li ripulisce al salvataggio
        setTimeout(() => this._sync());
    },

    _onDrop(ev) {
        const files = [...(ev.dataTransfer?.files || [])];
        if (files.length) {
            ev.preventDefault();
            const range = document.caretRangeFromPoint?.(ev.clientX, ev.clientY);
            if (range) {
                this.savedRange = range;
            }
            this._insertImages(files);
        }
    },

    // ---------------------------------------------------------------- invio
    _isEmpty() {
        return !this.editor.textContent.trim() && !this.editor.querySelector("img");
    },

    /** HTML da inviare, senza gli stili che il browser aggiunge da solo (es. font-size). */
    _value() {
        const clone = this.editor.cloneNode(true);
        clone.querySelectorAll("[style]").forEach((el) => el.removeAttribute("style"));
        clone.querySelectorAll("span, font").forEach((el) => el.replaceWith(...el.childNodes));
        // il browser a volte mette l'elenco dentro un paragrafo (<p><ul>…): non è HTML valido
        clone.querySelectorAll("p > ul, p > ol").forEach((list) => {
            const p = list.parentElement;
            p.replaceWith(...p.childNodes);
        });
        clone.querySelectorAll("p").forEach((p) => {
            if (!p.textContent.trim() && !p.querySelector("img, br")) {
                p.remove(); // paragrafi vuoti lasciati dagli elenchi
            }
        });
        return clone.innerHTML;
    },

    _sync() {
        this.textarea.value = this._isEmpty() ? "" : this._value();
        if (!this._isEmpty()) {
            this.editor.classList.remove("is-invalid");
        }
    },

    _onSendCapture(ev) {
        if (!ev.target.closest(".s_website_form_send, .o_website_form_send")) {
            return;
        }
        this._sync();
        if (this._isEmpty()) {
            ev.preventDefault();
            ev.stopPropagation();
            this.editor.classList.add("is-invalid");
            this.editor.focus();
            this._message("Scrivi la descrizione della richiesta.");
        }
    },

    _message(text) {
        this.hint.textContent = text;
        this.hint.classList.add("text-danger");
        clearTimeout(this._hintTimer);
        this._hintTimer = setTimeout(() => {
            this.hint.classList.remove("text-danger");
            this.hint.textContent = "Puoi usare grassetto, elenchi e link; le schermate si " +
                "incollano direttamente con Ctrl+V.";
        }, 6000);
    },
});

export default publicWidget.registry.LabHelpdeskRichDescription;
