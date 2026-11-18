# -*- coding: utf-8 -*-
from . import models

# Impostazioni standard di ogni cantina (le stesse che si attivano a mano da Impostazioni).
STANDARD_SETTINGS = {
    "group_product_pricelist": True,     # listini per tipo di cliente e valuta
    "group_stock_production_lot": True,  # lotti di imbottigliamento
    "group_stock_packaging": True,       # cartoni da 6 / 12
}


def _cs_post_init(env):
    settings = env["res.config.settings"].create(
        {k: v for k, v in STANDARD_SETTINGS.items() if k in env["res.config.settings"]._fields})
    settings.execute()
    # Il listino export in dollari ha bisogno della valuta attiva (il cambio lo mette il cliente).
    (env.ref("base.USD") | env.ref("base.EUR")).active = True
