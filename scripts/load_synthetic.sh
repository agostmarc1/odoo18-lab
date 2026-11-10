#!/usr/bin/env bash
# Carica i dati sintetici della software house nel database lab18 (idempotente: se ci sono gia' non fa nulla).
source "$(dirname "$0")/_lib.sh"
load_synthetic_data
set_passwords
