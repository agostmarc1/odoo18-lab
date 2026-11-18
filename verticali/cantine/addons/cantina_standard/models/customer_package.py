# -*- coding: utf-8 -*-
"""Caricamento dei dati di UNA cantina dalla sua cartella (cliente.json, vini.csv, clienti.csv).

È il punto che rende la soluzione ripetibile: il codice è lo stesso per tutte le cantine,
cambiano solo i file. Il caricamento è idempotente: crea ciò che manca e non tocca ciò che
la cantina ha già modificato (eccetto i dati dell'azienda, che arrivano sempre da cliente.json).
"""
import csv
import json
import logging
import os
import re
from datetime import date, datetime, time, timedelta

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

XMLID_MODULE = "cantina_cliente"   # i record del cliente hanno id esterni cantina_cliente.*
PRICELISTS = {                      # colonna di vini.csv / clienti.csv -> listino standard
    "italia": "cantina_standard.pl_italia",
    "horeca": "cantina_standard.pl_horeca",
    "export_eu": "cantina_standard.pl_export_eu",
    "export_usa": "cantina_standard.pl_export_usa",
}
CATEGORIES = {
    "rossi": "cantina_standard.categ_wine_red",
    "bianchi": "cantina_standard.categ_wine_white",
    "spumanti": "cantina_standard.categ_wine_sparkling",
}
ROLES = {  # ruolo in cliente.json -> gruppi standard di Odoo
    "titolare": ["sales_team.group_sale_manager", "stock.group_stock_manager",
                 "purchase.group_purchase_manager", "account.group_account_manager",
                 "event.group_event_manager", "base.group_partner_manager"],
    "commerciale": ["sales_team.group_sale_salesman_all_leads", "stock.group_stock_user",
                    "event.group_event_user", "base.group_partner_manager"],
    "magazzino": ["stock.group_stock_user", "purchase.group_purchase_user",
                  "sales_team.group_sale_salesman"],
}
FORMATS = {"0.375": "0.375", "0.5": "0.5", "0.75": "0.75", "1.5": "1.5", "3": "3.0", "3.0": "3.0",
           "5": "5.0", "5.0": "5.0", "6": "6.0", "6.0": "6.0"}


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def _num(value, default=0.0):
    value = (value or "").strip().replace(",", ".")
    return float(value) if value else default


class CsCustomerPackage(models.AbstractModel):
    _name = "cs.customer.package"
    _description = "Soluzione Cantina - caricamento dati del cliente"

    # ------------------------------------------------------------------
    # Lettura file
    # ------------------------------------------------------------------
    @api.model
    def _cs_read_json(self, path):
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError as exc:
            raise UserError(_("File mancante: %s", path)) from exc
        except json.JSONDecodeError as exc:
            raise UserError(_("%(f)s non è un JSON valido (riga %(r)s).", f=path, r=exc.lineno)) from exc

    @api.model
    def _cs_read_csv(self, path):
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(2048)
            handle.seek(0)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            return [{(k or "").strip(): (v or "").strip() for k, v in row.items()}
                    for row in csv.DictReader(handle, delimiter=delimiter) if any(row.values())]

    # ------------------------------------------------------------------
    # Utilità per l'idempotenza: ogni record del cliente ha un id esterno
    # ------------------------------------------------------------------
    @api.model
    def _cs_ref(self, name):
        return self.env.ref(f"{XMLID_MODULE}.{name}", raise_if_not_found=False)

    @api.model
    def _cs_create(self, name, model, vals):
        record = self._cs_ref(name)
        if record:
            return record, False
        record = self.env[model].create(vals)
        self.env["ir.model.data"].create({
            "module": XMLID_MODULE, "name": name, "model": model,
            "res_id": record.id, "noupdate": True,
        })
        return record, True

    # ------------------------------------------------------------------
    # Caricamento
    # ------------------------------------------------------------------
    @api.model
    def _cs_load(self, folder):
        """Carica (o completa) i dati della cantina dalla cartella. Restituisce un riepilogo."""
        data = self._cs_read_json(os.path.join(folder, "cliente.json"))
        self._cs_company(data)
        products = self._cs_wines(self._cs_read_csv(os.path.join(folder, "vini.csv")))
        partners = self._cs_customers(self._cs_read_csv(os.path.join(folder, "clienti.csv")))
        users = self._cs_users(data.get("utenti") or [])
        demo = self._cs_demo(data, folder, products, partners) if data.get("dati_demo") else []
        summary = {
            "azienda": self.env.company.name,
            "vini": len(products),
            "clienti": len(partners),
            "utenti": users.mapped("login"),
            "demo": demo,
        }
        _logger.info("Soluzione Cantina: dati caricati %s", summary)
        return summary

    @api.model
    def _cs_company(self, data):
        company = self.env.company
        vals = {k: data[j] for j, k in (("ragione_sociale", "name"), ("via", "street"), ("cap", "zip"),
                                        ("citta", "city"), ("email", "email"), ("telefono", "phone"),
                                        ("sito", "website")) if data.get(j)}
        country = self.env["res.country"].search([("code", "=", (data.get("paese") or "IT").upper())], limit=1)
        if country:
            vals["country_id"] = country.id
        if data.get("piva") and "vat" in company._fields:
            vals["vat"] = data["piva"]
        company.write(vals)
        # Cambio USD per il listino export: in produzione arriva dal servizio dei cambi.
        usd = self.env.ref("base.USD")
        rate = data.get("cambio_usd_dimostrativo")
        if rate and company.currency_id != usd and not self.env["res.currency.rate"].search_count(
                [("currency_id", "=", usd.id), ("company_id", "in", [company.id, False])]):
            self.env["res.currency.rate"].create({
                "currency_id": usd.id, "company_id": company.id,
                "name": date.today().replace(month=1, day=1), "rate": float(rate)})

    @api.model
    def _cs_named(self, model, name, extra=None):
        """Denominazione o vitigno per nome: se manca nell'anagrafica standard la crea."""
        if not name:
            return self.env[model]
        record = self.env[model].with_context(active_test=False).search([("name", "=ilike", name)], limit=1)
        return record or self.env[model].create(dict({"name": name}, **(extra or {})))

    @api.model
    def _cs_wines(self, rows):
        products = {}
        stock = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1).lot_stock_id
        for row in rows:
            code = row.get("codice")
            if not code:
                continue
            den = self._cs_named("lw.wine.denomination", row.get("denominazione"),
                                 {"level": (row.get("livello") or "doc").lower()})
            grape = self._cs_named("lw.wine.grape", row.get("vitigno"),
                                   {"color": "white" if row.get("categoria") == "bianchi" else "red"})
            vintage = int(_num(row.get("annata"))) if row.get("annata", "").isdigit() else 0
            per_case = int(_num(row.get("bott_cartone"), 6)) or 1
            gross = _num(row.get("peso_lordo"))
            categ = self.env.ref(CATEGORIES.get(row.get("categoria", "").lower(), "cantina_standard.categ_wine"))
            tmpl, created = self._cs_create("wine_" + _slug(code), "product.template", {
                "name": row.get("nome") or code,
                "default_code": code,
                "categ_id": categ.id,
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
                "sale_ok": True,
                "purchase_ok": False,
                "list_price": _num(row.get("prezzo_base")),
                "weight": gross,
                "lw_is_wine": True,
                "lw_vintage": vintage,
                "lw_denomination_id": den.id,
                "lw_grape_id": grape.id,
                "lw_grape_percent": _num(row.get("perc_vitigno"), 100.0),
                "lw_alcohol": _num(row.get("grado")),
                "lw_format": FORMATS.get((row.get("formato") or "0.75").replace(",", "."), "0.75"),
                "lw_bottles_per_case": per_case,
                "lw_bottle_net_kg": _num(row.get("peso_netto")),
                "lw_bottle_gross_kg": gross,
                "lw_case_tare_kg": _num(row.get("tara_cartone")),
                "lw_case_length_cm": _num(row.get("lung_cm")),
                "lw_case_width_cm": _num(row.get("larg_cm")),
                "lw_case_height_cm": _num(row.get("alt_cm")),
                "lw_producer_notes": row.get("note") or False,
            })
            product = tmpl.product_variant_id
            products[code] = product
            for column, xmlid in PRICELISTS.items():
                price = _num(row.get(column))
                pricelist = self.env.ref(xmlid)
                if price and not pricelist.item_ids.filtered(lambda i: i.product_tmpl_id == tmpl):
                    self.env["product.pricelist.item"].create({
                        "pricelist_id": pricelist.id, "applied_on": "1_product",
                        "product_tmpl_id": tmpl.id, "compute_price": "fixed", "fixed_price": price})
            if per_case > 1 and not product.packaging_ids:
                self.env["product.packaging"].create({
                    "name": _("Cartone da %s", per_case), "product_id": product.id, "qty": per_case})
            qty = _num(row.get("giacenza"))
            if created and qty > 0 and stock:   # giacenza iniziale: solo alla prima creazione
                lot = self.env["stock.lot"].create({
                    "name": row.get("lotto") or "L%s-01" % (vintage or "NV"),
                    "product_id": product.id, "company_id": self.env.company.id})
                self.env["stock.quant"].with_context(inventory_mode=True).create({
                    "product_id": product.id, "location_id": stock.id,
                    "lot_id": lot.id, "inventory_quantity": qty,
                }).action_apply_inventory()
        return products

    @api.model
    def _cs_customers(self, rows):
        partners = {}
        Lang = self.env["res.lang"]
        for row in rows:
            name = row.get("nome")
            if not name:
                continue
            country = self.env["res.country"].search([("code", "=", (row.get("paese") or "IT").upper())], limit=1)
            lang = Lang._activate_lang(row.get("lingua") or "it_IT").code  # vuoto se il codice non esiste
            pricelist = self.env.ref(PRICELISTS.get(row.get("listino"), "cantina_standard.pl_italia"))
            partner, _created = self._cs_create("partner_" + _slug(name), "res.partner", {
                "name": name, "is_company": True,
                "street": row.get("via") or False, "zip": row.get("cap") or False,
                "city": row.get("citta") or False, "country_id": country.id or False,
                "email": row.get("email") or False, "phone": row.get("telefono") or False,
                "lang": lang or False,
                "property_product_pricelist": pricelist.id,
                "customer_rank": 1,
            })
            partners[name] = partner
        return partners

    @api.model
    def _cs_users(self, rows):
        users = self.env["res.users"]
        for row in rows:
            login = row.get("login")
            if not login:
                continue
            groups = self.env.ref("base.group_user")
            for xmlid in ROLES.get(row.get("ruolo"), []):
                groups |= self.env.ref(xmlid, raise_if_not_found=False) or groups.browse()
            user, _created = self._cs_create("user_" + _slug(login), "res.users", {
                "name": row.get("nome") or login, "login": login,
                "email": row.get("email") or False,
                "groups_id": [(6, 0, groups.ids)],
                "tz": "Europe/Rome",
            })
            users |= user
        return users

    # ------------------------------------------------------------------
    # Dati dimostrativi: un preventivo da email, un ordine confermato, una degustazione
    # ------------------------------------------------------------------
    @api.model
    def _cs_demo(self, data, folder, products, partners):
        done = []
        email = data.get("ordine_da_email") or {}
        partner = partners.get(email.get("cliente"))
        path = os.path.join(folder, email.get("file") or "ordine_demo.txt")
        if partner and os.path.exists(path) and not self._cs_ref("demo_quote_email"):
            with open(path, encoding="utf-8") as handle:
                text = handle.read().strip()
            self._cs_create("demo_quote_email", "sale.order", {
                "partner_id": partner.id, "lw_raw_request": text})
            done.append("preventivo da email per %s" % partner.name)

        confirmed = data.get("ordine_confermato") or {}
        partner = partners.get(confirmed.get("cliente"))
        lines = [(products[c], q) for c, q in confirmed.get("righe") or [] if c in products]
        if partner and lines and not self._cs_ref("demo_order_confirmed"):
            order, _created = self._cs_create("demo_order_confirmed", "sale.order", {
                "partner_id": partner.id,
                "order_line": [(0, 0, {"product_id": p.id, "product_uom_qty": q}) for p, q in lines]})
            order.action_confirm()
            done.append("ordine %s confermato" % order.name)

        tasting = data.get("evento") or {}
        if tasting.get("nome") and not self._cs_ref("demo_event"):
            today = date.today()
            saturday = today - timedelta(days=(today.weekday() - 5) % 7 or 7)
            start = datetime.combine(saturday, time(9, 0))      # 11:00 in Italia (UTC+2 d'estate)
            event, _created = self._cs_create("demo_event", "event.event", {
                "name": tasting["nome"],
                "date_begin": start, "date_end": start + timedelta(hours=2),
                "date_tz": "Europe/Rome",
                "seats_max": int(tasting.get("posti") or 20), "seats_limited": True,
                # dati dimostrativi: niente email automatiche (biglietti, promemoria) ai visitatori finti
                "event_mail_ids": [(5, 0, 0)],
            })
            self.env["event.registration"].create([{
                "event_id": event.id, "name": "Visitatore %s" % i,
                "email": "visitatore%s@example.com" % i,
            } for i in range(1, int(tasting.get("partecipanti") or 0) + 1)])
            done.append("degustazione con %s partecipanti" % len(event.registration_ids))
        return done
