# Immagine del laboratorio: Odoo 18.0 Community ufficiale + le librerie Python richieste
# dalla localizzazione italiana OCA (l10n-italy 18.0). Nient'altro.
FROM odoo:18.0

USER root
COPY requirements.txt /tmp/lab-requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/lab-requirements.txt \
    && rm /tmp/lab-requirements.txt
USER odoo
