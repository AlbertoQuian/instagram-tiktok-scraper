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