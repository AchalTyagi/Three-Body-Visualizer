"""Horizons fetch behaviour when JPL's service misbehaves (no network is used)."""
import json
from urllib.error import HTTPError, URLError

import numpy as np
import pytest

import gravity_lab.ephemeris as ephemeris
from gravity_lab.ephemeris import HorizonsServerError, _looks_like_server_fault

# The exact failure text reported by a user when Horizons' backend was broken.
USER_REPORTED_ERROR = ("wldini(): missing required file\nLTKERNL; ;  ERROR in VLRDC: "
                       "Var not declared: IP_ADDR")

GOOD = {
    "signature": {"source": "NASA/JPL Horizons API", "version": "1.2"},
    "result": "$$SOE\n2450000.5 = A.D. 1995-Oct-09 00:00:00.0000 TDB\n"
              " X = 1.0E+00 Y = 2.0E+00 Z = 3.0E+00\n VX= 1.0E-02 VY= 2.0E-02 VZ= 3.0E-02\n$$EOE\n",
}


class FakeResponse:
    def __init__(self, body):
        self.body = body.encode("utf-8") if isinstance(body, str) else body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def install(monkeypatch, outcomes):
    """Each outcome is a payload dict, raw text, or an exception to raise."""
    calls, sleeps = [], []
    queue = list(outcomes)

    def fake_urlopen(request, timeout=20.0):
        calls.append(request.full_url)
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(json.dumps(outcome) if isinstance(outcome, dict) else outcome)

    monkeypatch.setattr(ephemeris, "urlopen", fake_urlopen)
    monkeypatch.setattr(ephemeris, "_sleep", sleeps.append)
    return calls, sleeps


def test_user_reported_backend_message_is_classified_as_server_fault():
    assert _looks_like_server_fault(USER_REPORTED_ERROR)
    assert not _looks_like_server_fault("No ephemeris for target body 'Foo'")
    assert not _looks_like_server_fault("Cannot interpret date. Please verify the input.")


def test_server_fault_then_success_is_retried_transparently(monkeypatch):
    calls, sleeps = install(monkeypatch, [{"error": USER_REPORTED_ERROR}, GOOD])
    state = ephemeris.fetch_horizons_body("Sun", "2026-10-21")
    np.testing.assert_allclose(state.position_au, (1.0, 2.0, 3.0))
    assert len(calls) == 2 and sleeps == [1.5]


def test_persistent_server_fault_raises_friendly_server_error(monkeypatch):
    calls, sleeps = install(monkeypatch, [{"error": USER_REPORTED_ERROR}])
    with pytest.raises(HorizonsServerError, match="server-side problem") as info:
        ephemeris.fetch_horizons_body("Sun", "2026-10-21")
    assert "try again later" in str(info.value) and "IP_ADDR" in str(info.value)
    assert len(calls) == 3 and sleeps == [1.5, 3.0]  # default: 2 retries, doubling delay
    assert isinstance(info.value, RuntimeError)  # existing handlers keep working


def test_fault_embedded_in_result_text_is_also_retried(monkeypatch):
    bad = {"signature": {"version": "1.2"}, "result": "WLDINI: error loading execution-control file."}
    calls, _ = install(monkeypatch, [bad, GOOD])
    ephemeris.fetch_horizons_body("Earth", "2026-10-21")
    assert len(calls) == 2


def test_request_errors_are_reported_immediately_without_retry(monkeypatch):
    calls, sleeps = install(monkeypatch, [{"error": "No ephemeris for target body"}])
    with pytest.raises(RuntimeError, match="JPL Horizons error for Earth") as info:
        ephemeris.fetch_horizons_body("Earth", "2026-10-21")
    assert not isinstance(info.value, HorizonsServerError)
    assert len(calls) == 1 and sleeps == []


def test_http_5xx_is_retried_but_4xx_is_not(monkeypatch):
    url = ephemeris.HORIZONS_URL
    calls, _ = install(monkeypatch, [HTTPError(url, 503, "Service Unavailable", {}, None), GOOD])
    ephemeris.fetch_horizons_body("Earth", "2026-10-21")
    assert len(calls) == 2
    calls, sleeps = install(monkeypatch, [HTTPError(url, 400, "Bad Request", {}, None)])
    with pytest.raises(RuntimeError, match="HTTP 400"):
        ephemeris.fetch_horizons_body("Earth", "2026-10-21")
    assert len(calls) == 1 and sleeps == []


def test_html_maintenance_page_is_treated_as_server_problem(monkeypatch):
    calls, _ = install(monkeypatch, ["<html><body>Down for maintenance</body></html>", GOOD])
    ephemeris.fetch_horizons_body("Earth", "2026-10-21")
    assert len(calls) == 2


def test_network_failure_is_not_reported_as_a_jpl_server_problem(monkeypatch):
    calls, _ = install(monkeypatch, [URLError("Name or service not known")])
    with pytest.raises(RuntimeError, match="Could not contact JPL Horizons") as info:
        ephemeris.fetch_horizons_body("Sun", "2026-10-21")
    assert not isinstance(info.value, HorizonsServerError)
    assert "internet connection" in str(info.value) and len(calls) == 3


def test_retries_can_be_disabled(monkeypatch):
    calls, sleeps = install(monkeypatch, [{"error": USER_REPORTED_ERROR}])
    with pytest.raises(HorizonsServerError):
        ephemeris.fetch_horizons_body("Sun", "2026-10-21", retries=0)
    assert len(calls) == 1 and sleeps == []


def test_three_body_import_stops_at_the_first_failing_body(monkeypatch):
    calls, _ = install(monkeypatch, [{"error": USER_REPORTED_ERROR}])
    with pytest.raises(HorizonsServerError):
        ephemeris.fetch_three_body_horizons(("Sun", "Earth", "Jupiter"), "2026-10-21")
    assert len(calls) == 3  # one body's attempts, not three bodies' worth
