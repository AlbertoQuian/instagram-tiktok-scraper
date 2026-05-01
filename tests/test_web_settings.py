"""Tests for the local web settings UI."""

from __future__ import annotations

import json

import web.app as web_app


def test_settings_page_keeps_dates_out_of_settings(monkeypatch, tmp_path):
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(json.dumps({"accounts": []}), encoding="utf-8")
    monkeypatch.setattr(web_app, "ACCOUNTS_FILE", accounts_file)

    response = web_app.app.test_client().get("/settings?lang=es")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Periodo predeterminado" not in html
    assert "Carpeta de guardado" in html
    assert "Elegir carpeta" in html


def test_settings_update_preserves_study_period(monkeypatch, tmp_path):
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(
        json.dumps(
            {
                "project": "Old",
                "study_period": {"start": "2024-01-01", "end": "2024-02-01"},
                "storage": {"data_dir": ""},
                "accounts": [],
            }
        ),
        encoding="utf-8",
    )
    data_dir = tmp_path / "selected-data"
    monkeypatch.setattr(web_app, "ACCOUNTS_FILE", accounts_file)

    response = web_app.app.test_client().post(
        "/api/settings/project?lang=es",
        json={"project": "New", "data_dir": str(data_dir)},
    )

    assert response.status_code == 200
    saved = json.loads(accounts_file.read_text(encoding="utf-8"))
    assert saved["project"] == "New"
    assert saved["study_period"] == {"start": "2024-01-01", "end": "2024-02-01"}
    assert saved["storage"] == {"data_dir": str(data_dir)}


def test_directory_picker_endpoint_returns_selected_path(monkeypatch, tmp_path):
    selected = tmp_path / "chosen"
    selected.mkdir()
    monkeypatch.setattr(
        web_app,
        "_choose_data_directory",
        lambda language: {"success": True, "path": str(selected), "message": "ok"},
    )

    response = web_app.app.test_client().post("/api/settings/choose-data-dir?lang=en", json={})

    assert response.status_code == 200
    assert response.get_json()["path"] == str(selected)


def test_dashboard_uses_saved_run_settings(monkeypatch, tmp_path):
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(
        json.dumps(
            {
                "project": "",
                "study_period": {"start": "2025-01-01", "end": "2025-02-01"},
                "run": {
                    "platform": "tiktok",
                    "limit_mode": "custom",
                    "custom_limit": "123",
                    "download_media": False,
                    "take_screenshots": True,
                    "export_after": False,
                },
                "accounts": [{"account_name": "Test", "instagram": "test_ig", "tiktok": "test_tt"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_app, "ACCOUNTS_FILE", accounts_file)

    response = web_app.app.test_client().get("/?lang=es")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<option value="tiktok" selected>TikTok</option>' in html
    assert 'id="run-max-posts" class="input compact-number" type="number" min="1" step="1" value="123"' in html
    assert 'id="run-start" class="input" type="date" value="2025-01-01"' in html
    assert 'id="run-end" class="input" type="date" value="2025-02-01"' in html
    assert "Cantidad personalizada" in html
    assert "Sin límite" in html
    assert "Alcance" not in html
    assert "Prueba rápida" not in html
    assert "Trabajo normal" not in html


def test_run_settings_autosave_updates_config(monkeypatch, tmp_path):
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(json.dumps({"accounts": []}), encoding="utf-8")
    monkeypatch.setattr(web_app, "ACCOUNTS_FILE", accounts_file)

    response = web_app.app.test_client().post(
        "/api/settings/run?lang=es",
        json={
            "platform": "instagram",
            "start_date": "2025-03-01",
            "end_date": "2025-03-31",
            "limit_mode": "custom",
            "custom_limit": "75",
            "download_media": False,
            "take_screenshots": True,
            "export_after": False,
        },
    )

    assert response.status_code == 200
    saved = json.loads(accounts_file.read_text(encoding="utf-8"))
    assert saved["study_period"] == {"start": "2025-03-01", "end": "2025-03-31"}
    assert saved["run"] == {
        "platform": "instagram",
        "limit_mode": "custom",
        "custom_limit": "75",
        "download_media": False,
        "take_screenshots": True,
        "export_after": False,
    }


def test_legacy_numeric_limit_becomes_custom(monkeypatch, tmp_path):
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(
        json.dumps({"run": {"platform": "all", "limit_mode": "50"}, "accounts": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_app, "ACCOUNTS_FILE", accounts_file)

    response = web_app.app.test_client().get("/?lang=es")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="run-max-posts" class="input compact-number" type="number" min="1" step="1" value="50"' in html


def test_no_limit_is_same_quantity_control(monkeypatch, tmp_path):
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(
        json.dumps({"run": {"limit_mode": "0", "custom_limit": "200"}, "accounts": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_app, "ACCOUNTS_FILE", accounts_file)

    response = web_app.app.test_client().get("/?lang=es")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="run-limit-none" name="run-limit-mode" type="radio" value="0" checked' in html
    assert 'id="run-max-posts" class="input compact-number" type="number" min="1" step="1" value="200" placeholder="200" disabled' in html
    assert "Alcance" not in html


def test_connections_page_explains_tiktok_optional(monkeypatch, tmp_path):
    instagram_path = tmp_path / "instagram_cookies.json"
    tiktok_path = tmp_path / "tiktok_cookies.txt"
    monkeypatch.setitem(web_app.INSTAGRAM_SETTINGS, "cookies_path", instagram_path)
    monkeypatch.setitem(web_app.TIKTOK_SETTINGS, "cookies_path", tiktok_path)

    response = web_app.app.test_client().get("/cookies?lang=es")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'class="content-grid two-columns cookies-grid"' in html
    assert "Opcional; no conectada" in html
    assert "Si no tienes cuenta" in html