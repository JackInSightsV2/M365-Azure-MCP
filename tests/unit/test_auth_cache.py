import time

import pytest
from azure.core.credentials import AccessToken

from unified_mcp.auth import DeviceCodeProfile, ServicePrincipalProfile, TokenBroker


class RecordingCredential:
    """Credential that exposes an ``_auth_record`` like DeviceCodeCredential."""

    def __init__(self, record: object | None = "auth-record") -> None:
        self._auth_record = record

    def get_token(self, *_scopes: str) -> AccessToken:
        return AccessToken("token", int(time.time()) + 3600)


@pytest.mark.asyncio
async def test_device_profile_persists_auth_record_once(tmp_path):
    path = str(tmp_path / "arm.json")
    saved: list[tuple[str | None, object]] = []
    profile = DeviceCodeProfile("t", "c", ("s",), auth_record_path=path)
    broker = TokenBroker(
        profile,
        lambda *_a: None,
        credential_factory=lambda _p, _c: RecordingCredential(),
    )

    import unified_mcp.auth as auth_module

    original = auth_module.save_auth_record
    auth_module.save_auth_record = lambda p, r: saved.append((p, r))
    try:
        await broker.get_token()
        # A second acquisition (forced) must not persist again.
        broker._cached_token = None
        await broker.get_token()
    finally:
        auth_module.save_auth_record = original

    assert saved == [(path, "auth-record")]


@pytest.mark.asyncio
async def test_cache_disabled_skips_persistence(tmp_path):
    saved: list = []
    profile = DeviceCodeProfile(
        "t", "c", ("s",), cache_enabled=False, auth_record_path=str(tmp_path / "x.json")
    )
    broker = TokenBroker(
        profile,
        lambda *_a: None,
        credential_factory=lambda _p, _c: RecordingCredential(),
    )

    import unified_mcp.auth as auth_module

    original = auth_module.save_auth_record
    auth_module.save_auth_record = lambda p, r: saved.append((p, r))
    try:
        await broker.get_token()
    finally:
        auth_module.save_auth_record = original

    assert saved == []


@pytest.mark.asyncio
async def test_non_device_profile_skips_persistence():
    saved: list = []
    profile = ServicePrincipalProfile("t", "c", "secret", scopes=("s",))
    broker = TokenBroker(
        profile,
        lambda *_a: None,
        credential_factory=lambda _p, _c: RecordingCredential(),
    )

    import unified_mcp.auth as auth_module

    original = auth_module.save_auth_record
    auth_module.save_auth_record = lambda p, r: saved.append((p, r))
    try:
        await broker.get_token()
    finally:
        auth_module.save_auth_record = original

    assert saved == []
