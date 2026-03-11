import importlib
import sys


def load_storage_module(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_USER_ID", "123")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    sys.modules.pop("config", None)
    sys.modules.pop("storage", None)

    import storage

    return importlib.reload(storage)


def test_add_wallet_includes_default_funding_filters(monkeypatch, tmp_path):
    storage = load_storage_module(monkeypatch, tmp_path)

    assert storage.add_wallet("0xabc")

    filters = storage.get_funding_filters("0xabc")
    assert filters == {
        "annualized_threshold": None,
        "usdc_threshold": None,
    }


def test_set_funding_filters_supports_off(monkeypatch, tmp_path):
    storage = load_storage_module(monkeypatch, tmp_path)
    storage.add_wallet("0xabc")

    updated = storage.set_funding_filters("0xabc", None, 7.5)

    assert updated == {
        "annualized_threshold": None,
        "usdc_threshold": 7.5,
    }
