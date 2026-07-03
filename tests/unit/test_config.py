from services.shared.config import get_settings


def test_cors_origins_accept_render_env_name(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("CORS_ORIGINS", "https://conduitwallet.com, https://preview.example")

    settings = get_settings()

    assert settings.cors_origins == ["https://conduitwallet.com", "https://preview.example"]
    assert settings.cors_origin_list == settings.cors_origins
    get_settings.cache_clear()


def test_cors_origins_prefer_explicit_allowed_name(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("CORS_ORIGINS", "https://from-render.example")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://from-env.example")

    assert get_settings().cors_origins == ["https://from-env.example"]
    get_settings.cache_clear()
