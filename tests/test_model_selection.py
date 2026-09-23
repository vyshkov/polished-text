from unittest.mock import MagicMock, patch

from dictation_app.config import (
    AVAILABLE_CORRECTOR_MODELS,
    AVAILABLE_MODELS,
    get_model_display_name,
    get_model_info,
    get_model_subtitle,
    save_corrector_model_to_env,
    save_model_to_env,
)
from dictation_app.engine import DictationEngine
from dictation_app.menubar import DictationMenuBar


def test_available_models_structure():
    assert len(AVAILABLE_MODELS) >= 8
    model_ids = [mid for mid, _ in AVAILABLE_MODELS]
    assert "azure-speech" in model_ids
    assert "gemini-3.8-flash" in model_ids
    assert "gemini-3.7-flash" in model_ids
    assert "gemini-3.6-flash" in model_ids
    assert "gemini-3.5-flash" in model_ids
    assert "gemini-3.5-flash-lite" in model_ids


def test_get_model_display_name():
    assert "Azure Speech" in get_model_display_name("azure-speech")
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


@patch("dictation_app.engine.save_model_to_env")
@patch("dictation_app.engine.get_transcriber")
def test_engine_set_model_azure(mock_get_transcriber, mock_save_env):
    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.6-flash")
        engine.hud = MagicMock()

        engine.set_model("azure-speech")

        assert engine.model == "azure-speech"
        mock_save_env.assert_called_once_with("azure-speech")
        mock_get_transcriber.assert_called_with(model="azure-speech")
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


def test_available_corrector_models_structure():
    assert len(AVAILABLE_CORRECTOR_MODELS) >= 5
    model_ids = [mid for mid, _ in AVAILABLE_CORRECTOR_MODELS]
    assert "gemini-3.5-flash-lite" in model_ids
    assert "gemini-3.6-flash" in model_ids
    assert "gemini-3.8-flash" in model_ids
    # Audio-only models should NOT be present in corrector models
    assert "azure-speech" not in model_ids
    assert "gemini-3.5-transcribe" not in model_ids


def test_save_corrector_model_to_env_updates_existing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nGEMINI_CORRECTOR_MODEL=gemini-3.5-flash-lite\nBAZ=1\n")

    assert save_corrector_model_to_env("gemini-3.6-flash", env_path=env_file) is True
    content = env_file.read_text()
    assert "GEMINI_CORRECTOR_MODEL=gemini-3.6-flash" in content
    assert "FOO=bar" in content
    assert "gemini-3.5-flash-lite" not in content


def test_save_corrector_model_to_env_preserves_export(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("export GEMINI_CORRECTOR_MODEL=gemini-3.5-flash-lite\n")

    assert save_corrector_model_to_env("gemini-3.6-flash", env_path=env_file) is True
    content = env_file.read_text()
    assert content == "export GEMINI_CORRECTOR_MODEL=gemini-3.6-flash\n"


def test_menubar_on_select_corrector_model_triggers_callback():
    history_mock = MagicMock()
    callback_mock = MagicMock()
    menubar = DictationMenuBar(
        history=history_mock,
        get_current_corrector_model=lambda: "gemini-3.5-flash-lite",
        on_select_corrector_model_callback=callback_mock,
        enabled=False,
    )
    with patch("dictation_app.menubar.play_sound"):
        menubar.on_select_corrector_model("gemini-3.6-flash")

    callback_mock.assert_called_once_with("gemini-3.6-flash")


@patch("dictation_app.engine.save_corrector_model_to_env")
@patch("dictation_app.engine.GeminiCorrector")
def test_engine_set_corrector_model(mock_corrector_cls, mock_save_env):
    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(corrector_model="gemini-3.5-flash-lite")
        engine.hud = MagicMock()

        engine.set_corrector_model("gemini-3.6-flash")

        assert engine.corrector_model == "gemini-3.6-flash"
        mock_save_env.assert_called_once_with("gemini-3.6-flash")
        mock_corrector_cls.assert_called_with(model="gemini-3.6-flash")
        engine.hud.show_done.assert_called_once()


def test_model_metadata_and_subtitles():
    # Every dictation model has use_case and limits
    for model_id, _ in AVAILABLE_MODELS:
        info = get_model_info(model_id, category="dictation")
        assert info.get("use_case")
        assert info.get("limits")
        subtitle = get_model_subtitle(model_id, category="dictation")
        assert "•" in subtitle
        assert info["use_case"] in subtitle
        assert info["limits"] in subtitle

    # Every corrector model has use_case and limits
    for model_id, _ in AVAILABLE_CORRECTOR_MODELS:
        info = get_model_info(model_id, category="polish")
        assert info.get("use_case")
        assert info.get("limits")
        subtitle = get_model_subtitle(model_id, category="polish")
        assert "•" in subtitle
        assert info["use_case"] in subtitle
        assert info["limits"] in subtitle

    # Unknown model fallback
    unknown_info = get_model_info("unknown-model-xyz")
    assert "use_case" in unknown_info
    assert "limits" in unknown_info
    assert "•" in get_model_subtitle("unknown-model-xyz")


def test_menubar_model_subtitles_and_tooltips():
    history_mock = MagicMock()
    menubar = DictationMenuBar(
        history=history_mock,
        get_current_model=lambda: "groq:whisper-large-v3-turbo",
        get_current_corrector_model=lambda: "groq:openai/gpt-oss-120b",
        enabled=True,
    )

    # Find Dictation Model menu item and inspect its submenu
    items = menubar.menu.itemArray()
    dict_item = next((it for it in items if "Dictation Model:" in it.title()), None)
    assert dict_item is not None
    if hasattr(dict_item, "subtitle"):
        assert "Ultra-fast" in dict_item.subtitle()

    dict_sub = dict_item.submenu()
    assert dict_sub is not None
    sub_items = dict_sub.itemArray()
    assert len(sub_items) == len(AVAILABLE_MODELS)

    # Check each sub_item has subtitle and toolTip
    for sub_it in sub_items:
        model_id = sub_it.representedObject()
        info = get_model_info(model_id, category="dictation")
        if hasattr(sub_it, "subtitle"):
            assert sub_it.subtitle() == f"{info['use_case']} • {info['limits']}"
        assert info["use_case"] in sub_it.toolTip()
        assert info["limits"] in sub_it.toolTip()

    # Find Polish Model menu item and inspect its submenu
    corr_item = next((it for it in items if "Polish Model:" in it.title()), None)
    assert corr_item is not None
    if hasattr(corr_item, "subtitle"):
        assert "Nuanced copy" in corr_item.subtitle()

    corr_sub = corr_item.submenu()
    assert corr_sub is not None
    corr_sub_items = corr_sub.itemArray()
    assert len(corr_sub_items) == len(AVAILABLE_CORRECTOR_MODELS)

    for sub_it in corr_sub_items:
        model_id = sub_it.representedObject()
        info = get_model_info(model_id, category="polish")
        if hasattr(sub_it, "subtitle"):
            assert sub_it.subtitle() == f"{info['use_case']} • {info['limits']}"
        assert info["use_case"] in sub_it.toolTip()
        assert info["limits"] in sub_it.toolTip()
