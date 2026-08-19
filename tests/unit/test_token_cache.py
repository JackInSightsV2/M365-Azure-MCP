import os
import stat

from azure.identity import AuthenticationRecord

from unified_mcp.token_cache import load_auth_record, save_auth_record


def _record() -> AuthenticationRecord:
    return AuthenticationRecord(
        "tenant-id",
        "client-id",
        "https://login.microsoftonline.com",
        "home-account-id",
        "user@example.com",
    )


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "nested" / "auth-record.json")

    save_auth_record(path, _record())
    loaded = load_auth_record(path)

    assert loaded is not None
    assert loaded.home_account_id == "home-account-id"
    assert loaded.username == "user@example.com"


def test_saved_record_is_owner_only(tmp_path):
    path = str(tmp_path / "auth-record.json")

    save_auth_record(path, _record())

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_load_missing_path_returns_none(tmp_path):
    assert load_auth_record(str(tmp_path / "absent.json")) is None
    assert load_auth_record(None) is None


def test_load_corrupt_record_returns_none(tmp_path):
    path = tmp_path / "auth-record.json"
    path.write_text("not-json")

    assert load_auth_record(str(path)) is None


def test_save_with_empty_path_is_noop(tmp_path):
    # Must not raise when persistence is disabled.
    save_auth_record(None, _record())
    save_auth_record("", _record())
