from odoo import api, models


class SaleSubscription(models.Model):
    _inherit = "sale.subscription"

    @api.model_create_multi
    def create(self, vals_list):
        # subscription_oca richiede un listino, ma in Odoo 18 l'ordine può non averlo
        # (listini disattivati): usiamo quello del cliente o il primo disponibile.
        for vals in vals_list:
            if not vals.get("pricelist_id"):
                partner = self.env["res.partner"].browse(vals.get("partner_id"))
                pricelist = partner.property_product_pricelist or self.env[
                    "product.pricelist"].search([], limit=1)
                if not pricelist:
                    pricelist = self.env["product.pricelist"].sudo().create(
                        {"name": "Listino predefinito"})
                vals["pricelist_id"] = pricelist.id
        return super().create(vals_list)
