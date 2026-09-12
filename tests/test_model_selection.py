from unittest.mock import MagicMock, patch

from dictation_app.config import (
    AVAILABLE_MODELS,
    get_model_display_name,
    save_model_to_env,
)
from dictation_app.engine import DictationEngine
from dictation_app.menubar import DictationMenuBar


def test_available_models_structure():
    assert len(AVAILABLE_MODELS) >= 8
    model_ids = [mid for mid, _ in AVAILABLE_MODELS]
    assert "gemini-3.8-flash" in model_ids
    assert "gemini-3.7-flash" in model_ids
    assert "gemini-3.6-flash" in model_ids
    assert "gemini-3.5-flash" in model_ids
    assert "gemini-3.5-flash-lite" in model_ids


def test_get_model_display_name():
    assert "3.8 Flash" in get_model_display_name("gemini-3.8-flash")
    assert "3.7 Flash" in get_model_display_name("gemini-3.7-flash")
    assert "3.6 Flash" in get_model_display_name("gemini-3.6-flash")
    assert "3.5 Flash Lite" in get_model_display_name("gemini-3.5-flash-lite")
    # Unknown model falls back to ID
    assert get_model_display_name("custom-model-x") == "custom-model-x"


def test_save_model_to_env_updates_existing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nGEMINI_MODEL=gemini-3.5-flash-lite\nBAZ=1\n")

    assert save_model_to_env("gemini-3.6-flash", env_path=env_file) is True
    content = env_file.read_text()
    assert "GEMINI_MODEL=gemini-3.6-flash" in content
    assert "FOO=bar" in content
    assert "BAZ=1" in content
    assert "gemini-3.5-flash-lite" not in content


def test_save_model_to_env_preserves_export_prefix(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("export GEMINI_MODEL=gemini-3.5-flash\n")

    assert save_model_to_env("gemini-3.6-flash", env_path=env_file) is True
    content = env_file.read_text()
    assert content == "export GEMINI_MODEL=gemini-3.6-flash\n"


def test_save_model_to_env_appends_when_absent(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\n")

    assert save_model_to_env("gemini-3.6-flash", env_path=env_file) is True
    content = env_file.read_text()
    assert "FOO=bar\n" in content
    assert "GEMINI_MODEL=gemini-3.6-flash\n" in content


def test_save_model_to_env_creates_file(tmp_path):
    env_file = tmp_path / "subdir" / ".env"
    assert save_model_to_env("gemini-3.6-flash", env_path=env_file) is True
    assert env_file.exists()
    assert env_file.read_text() == "GEMINI_MODEL=gemini-3.6-flash\n"


def test_menubar_on_select_model_triggers_callback():
    history_mock = MagicMock()
    callback_mock = MagicMock()
    menubar = DictationMenuBar(
        history=history_mock,
        get_current_model=lambda: "gemini-3.6-flash",
        on_select_model_callback=callback_mock,
        enabled=False,
    )
    with patch("dictation_app.menubar.play_sound"):
        menubar.on_select_model("gemini-3.5-flash-lite")

    callback_mock.assert_called_once_with("gemini-3.5-flash-lite")


@patch("dictation_app.engine.save_model_to_env")
@patch("dictation_app.engine.GeminiTranscriber")
def test_engine_set_model(mock_transcriber_cls, mock_save_env):
    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.5-flash-lite")
        engine.hud = MagicMock()

        engine.set_model("gemini-3.6-flash")

        assert engine.model == "gemini-3.6-flash"
        mock_save_env.assert_called_once_with("gemini-3.6-flash")
        mock_transcriber_cls.assert_called_with(model="gemini-3.6-flash")
        engine.hud.show_done.assert_called_once()


def test_get_model_thinking_config():
    from dictation_app.transcriber import get_model_thinking_config

    cfg_38 = get_model_thinking_config("gemini-3.8-flash")
    assert cfg_38 is not None
    assert cfg_38.thinking_budget == 0

    cfg_37 = get_model_thinking_config("gemini-3.7-flash")
    assert cfg_37 is not None
    assert cfg_37.thinking_budget == 0

    cfg_36 = get_model_thinking_config("gemini-3.6-flash")
    assert cfg_36 is not None
    assert str(cfg_36.thinking_level).upper() in ("MINIMAL", "THINKINGLEVEL.MINIMAL")

    cfg_transcribe = get_model_thinking_config("gemini-3.5-transcribe")
    assert cfg_transcribe is None
