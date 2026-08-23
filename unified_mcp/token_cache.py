"""Persistence for device-code authentication records.

The MSAL token cache (managed by ``azure-identity``) stores refresh tokens on disk,
but a credential can only *silently* reuse them when it is reconstructed with the
matching :class:`~azure.identity.AuthenticationRecord`. Persisting that record is
what turns device login from a per-restart prompt into a one-time sign-in.

The record itself contains no secrets: it holds the account identifier, username,
tenant, authority, and client id. Tokens live only in the MSAL cache file.
"""

from __future__ import annotations

import logging
import os

from azure.identity import AuthenticationRecord

logger = logging.getLogger(__name__)


def load_auth_record(path: str | None) -> AuthenticationRecord | None:
    """Load a persisted authentication record, or ``None`` when unavailable."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return AuthenticationRecord.deserialize(handle.read())
    except Exception as error:  # noqa: BLE001 - a bad cache must never block sign-in
        logger.warning("Ignoring unreadable authentication record at %s: %s", path, error)
        return None


def save_auth_record(path: str | None, record: AuthenticationRecord) -> None:
    """Persist an authentication record with owner-only permissions."""
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(record.serialize())
        logger.info("Persisted device authentication record to %s", path)
    except Exception as error:  # noqa: BLE001 - persistence is best effort
        logger.warning("Could not persist authentication record to %s: %s", path, error)
