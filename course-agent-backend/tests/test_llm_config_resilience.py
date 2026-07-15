from types import SimpleNamespace

from app.services import llm_config_service


def test_invalid_saved_llm_secret_returns_reconfiguration_state(monkeypatch):
    config = SimpleNamespace(
        api_key_encrypted="stale-token",
        enabled=True,
        provider="deepseek",
        model_name="deepseek-chat",
        base_url="https://api.deepseek.com",
    )

    def fail_decrypt(_value):
        raise RuntimeError("cannot decrypt")

    monkeypatch.setattr(llm_config_service, "decrypt_secret", fail_decrypt)
    result = llm_config_service.serialize_llm_config(config)

    assert result["configured"] is False
    assert result["enabled"] is False
    assert result["invalid"] is True
    assert "重新接入" in result["error_message"]
    assert result["api_key_hint"] is None
