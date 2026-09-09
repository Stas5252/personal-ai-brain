"""Production configuration must fail closed before a container starts."""
from scripts.validate_environment import collect_errors


def valid_env():
    return {
        "BRAIN_API_KEY": "a" * 48,
        "GEMINI_API_KEY": "gemini-test-value",
        "TELEGRAM_BOT_TOKEN": "123456789:telegram-test-token-value",
        "MAX_FILE_SIZE_BYTES": "20971520",
    }


def test_api_configuration_accepts_distinct_secrets():
    assert collect_errors("api", valid_env()) == []


def test_missing_and_known_placeholder_api_keys_are_rejected():
    env = valid_env()
    env["BRAIN_API_KEY"] = ""
    assert any("BRAIN_API_KEY" in item for item in collect_errors("api", env))
    env["BRAIN_API_KEY"] = "brain-secure-stage5-federation-key-2026"
    assert any("BRAIN_API_KEY" in item for item in collect_errors("api", env))


def test_telegram_requires_token_and_gemini_key():
    env = valid_env()
    env["TELEGRAM_BOT_TOKEN"] = ""
    env["GEMINI_API_KEY"] = ""
    errors = collect_errors("telegram", env)
    assert any("TELEGRAM_BOT_TOKEN" in item for item in errors)
    assert any("GEMINI_API_KEY" in item for item in errors)


def test_api_key_cannot_reuse_provider_or_bot_secret():
    env = valid_env()
    env["GEMINI_API_KEY"] = env["BRAIN_API_KEY"]
    assert any("different" in item for item in collect_errors("api", env))


def test_upload_limit_is_bounded_and_numeric():
    env = valid_env()
    env["MAX_FILE_SIZE_BYTES"] = "not-a-number"
    assert any("integer" in item for item in collect_errors("api", env))
    env["MAX_FILE_SIZE_BYTES"] = str(3 * 1024 * 1024 * 1024)
    assert any("2 GiB" in item for item in collect_errors("api", env))
