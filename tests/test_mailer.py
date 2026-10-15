from types import SimpleNamespace

from conftest import LOCAL_DATE, NOW

from spectro_alerts import mailer, run


def _payload(cfg):
    return run.build(cfg, run.collect(cfg, NOW), NOW, LOCAL_DATE, {"objects": {}})


def test_subject_and_bodies_cover_every_section(cfg, fake_http):
    p = _payload(cfg)
    p["weather"] = {"verdict": "GO", "line": "GO: clear 21:00-00:00", "clear_outside_url": "x"}
    assert mailer.subject(p) == "SPECTRO ALERT: YES, good skies? YES"
    p["weather"]["verdict"] = "MAYBE"
    assert mailer.subject(p) == "SPECTRO ALERT: YES, good skies? MAYBE"
    p["weather"]["verdict"] = "GO"
    text = mailer.text_body(p)
    assert "TCP J02191736+2857158" in text and "spectrum already reported" in text
    assert "Bright but poorly placed" in text and "SN 2026afaa" in text
    html = mailer.html_body(p)
    assert "GO: clear 21:00-00:00" in html and "<b>TCP J02191736+2857158</b>" in html


def test_send_posts_to_resend_and_reports_errors(cfg, fake_http, monkeypatch):
    p = _payload(cfg)
    sent = {}

    def post(url, headers, json, timeout):
        sent.update(url=url, auth=headers["Authorization"], body=json)
        return SimpleNamespace(status_code=200, json=lambda: {"id": "abc"}, text="")

    monkeypatch.setattr(mailer.requests, "post", post)
    assert mailer.send(p, "key123", "me@example.com") == "abc"
    assert sent["auth"] == "Bearer key123" and sent["body"]["to"] == ["me@example.com"]

    monkeypatch.setattr(
        mailer.requests,
        "post",
        lambda *a, **k: SimpleNamespace(status_code=403, text="invalid to", json=dict),
    )
    try:
        mailer.send(p, "key123", "me@example.com")
        raise AssertionError("expected an error")
    except RuntimeError as exc:
        assert "403" in str(exc)


def test_missing_secrets_fail_cleanly(tmp_path, monkeypatch, cfg, fake_http):
    import json

    f = tmp_path / "c.json"
    f.write_text(json.dumps(_payload(cfg)))
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert mailer.main(["--json", str(f)]) == 1


def test_no_targets_means_no_email(tmp_path, monkeypatch, cfg, fake_http):
    import json

    p = _payload(cfg)
    p["targets"] = []
    f = tmp_path / "c.json"
    f.write_text(json.dumps(p))
    monkeypatch.setenv("EMAIL_TO", "me@example.com")
    monkeypatch.setenv("RESEND_API_KEY", "k")
    calls = []
    monkeypatch.setattr(mailer, "send", lambda *a: calls.append(a) or "id")
    assert mailer.main(["--json", str(f)]) == 0 and calls == []
    assert mailer.main(["--json", str(f), "--always"]) == 0 and len(calls) == 1
