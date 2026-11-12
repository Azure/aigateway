"""Transport behaviour.

A collection is dozens of serial round trips. How the client behaves when one of
them misbehaves decides whether the whole run survives.
"""

import urllib.error

import pytest

from apim_import.arm import ArmClient, ArmError, _reason


class _Client(ArmClient):
    """An ArmClient with a canned transport and no token acquisition."""

    def __init__(self, failures, **kwargs):
        super().__init__(**kwargs)
        self._failures = list(failures)
        self.attempts = 0
        self._token = "token"
        self._token_expiry = 2**31

    def _open(self, *_args, **_kwargs):
        self.attempts += 1
        if self._failures:
            raise self._failures.pop(0)
        return _Response()


class _Response:
    status = 200
    headers: dict = {}

    def read(self):
        return b'{"value": []}'

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("apim_import.arm.time.sleep", lambda _seconds: None)


def client(failures, **kwargs):
    instance = _Client(failures, **kwargs)
    import apim_import.arm as arm

    # Route urlopen through the canned transport.
    original = arm.urllib.request.urlopen
    arm.urllib.request.urlopen = instance._open
    instance._restore = lambda: setattr(arm.urllib.request, "urlopen", original)
    return instance


class TestTransportErrors:
    """Regression: a socket timeout escaped uncaught and aborted a collection.

    TimeoutError is an OSError, not a URLError, so catching only URLError let it
    propagate out of request() and kill the whole run.
    """

    def test_a_socket_timeout_is_retried_not_raised(self):
        arm_client = client([TimeoutError("timed out"), TimeoutError("timed out")])
        try:
            response = arm_client.request("GET", "/subscriptions/x", api_version="2025-09-01-preview")
            assert response.ok
            assert arm_client.attempts == 3
        finally:
            arm_client._restore()

    def test_a_connection_error_is_retried(self):
        arm_client = client([ConnectionResetError("reset")])
        try:
            assert arm_client.request("GET", "/x", api_version="v").ok
        finally:
            arm_client._restore()

    def test_a_url_error_is_still_retried(self):
        arm_client = client([urllib.error.URLError("unreachable")])
        try:
            assert arm_client.request("GET", "/x", api_version="v").ok
        finally:
            arm_client._restore()

    def test_exhausting_retries_raises_a_clear_error_not_a_traceback(self):
        arm_client = client([TimeoutError("timed out")] * 10, max_retries=2)
        try:
            with pytest.raises(ArmError) as excinfo:
                arm_client.request("GET", "/subscriptions/x", api_version="v")
            assert "timed out" in str(excinfo.value)
            assert arm_client.attempts == 3  # the first try plus two retries
        finally:
            arm_client._restore()

    def test_retries_are_bounded(self):
        arm_client = client([TimeoutError("t")] * 50, max_retries=3)
        try:
            with pytest.raises(ArmError):
                arm_client.request("GET", "/x", api_version="v")
            assert arm_client.attempts == 4
        finally:
            arm_client._restore()


class TestReason:
    def test_url_error_reports_its_reason(self):
        assert _reason(urllib.error.URLError("unreachable")) == "unreachable"

    def test_a_bare_timeout_still_reports_something(self):
        assert _reason(TimeoutError()) == "TimeoutError"
        assert _reason(TimeoutError("timed out")) == "timed out"
