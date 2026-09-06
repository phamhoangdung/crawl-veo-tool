from unittest.mock import patch

from app.services import cost_service


def test_estimate_batch_cost_free_when_no_keys_configured(dummy_session):
    with patch("app.services.cost_service.api_key_service.get_decrypted_key", return_value=None):
        result = cost_service.estimate_batch_cost(dummy_session, user_id=1, total_duration_seconds=600)

    assert result["translate_provider"] == "google (free)"
    assert result["tts_provider"] == "edge-tts (free)"
    assert result["total_cost_usd"] == 0.0
    assert result["warning"] is None


def test_estimate_batch_cost_uses_paid_providers_when_keys_configured(dummy_session):
    def fake_get_key(_db, _user_id, provider):
        return "fake-key" if provider in ("openai", "elevenlabs") else None

    with patch("app.services.cost_service.api_key_service.get_decrypted_key", side_effect=fake_get_key):
        result = cost_service.estimate_batch_cost(dummy_session, user_id=1, total_duration_seconds=3600)

    assert result["translate_provider"] == "openai"
    assert result["tts_provider"] == "elevenlabs"
    assert result["total_cost_usd"] > 0
    assert result["warning"] is not None
