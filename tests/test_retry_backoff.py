import types

import config
from tts import _compute_backoff


class DummyResp:
    def __init__(self, headers):
        self.headers = headers


class DummyErr(Exception):
    def __init__(self, headers=None):
        super().__init__("dummy")
        self.response = types.SimpleNamespace(headers=headers or {})


def test_backoff_honors_retry_after():
    e = DummyErr(headers={"retry-after": "2.5"})
    assert _compute_backoff(e, 0) == 2.5


def test_backoff_exponential_no_jitter(monkeypatch):
    # Remove jitter for determinism
    monkeypatch.setattr("tts.random.uniform", lambda a, b: 0.0)
    base = max(1.0, float(getattr(config, "RETRY_DELAY", 5)))
    # attempt 0 -> base * 2**0
    assert _compute_backoff(DummyErr(), 0) == base
    # attempt 2 -> base * 2**2
    assert _compute_backoff(DummyErr(), 2) == base * 4
