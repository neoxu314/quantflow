"""Inherited by CLI and E2E server processes launched from pytest."""

import os

from network_guard import NETWORK_LOG, install

if os.environ.get(NETWORK_LOG):
    try:
        install(setattr)
    except Exception as exc:
        raise SystemExit("Could not enable the QuantFlow test network guard") from exc
