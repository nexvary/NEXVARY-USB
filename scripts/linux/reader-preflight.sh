#!/usr/bin/env bash
set -eu
# Read-only host inspection. No systemctl restart, routes, Outline or firewall edits.
python3 -m nexvary_usim_lab ports
command -v pcscd || true
systemctl status pcscd.socket pcscd.service --no-pager || true
ss -ltn || true
