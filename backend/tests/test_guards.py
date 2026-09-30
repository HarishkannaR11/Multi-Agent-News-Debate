import pytest
from guardrails.errors import ValidationError

from backend.config import settings
from backend.graph.guardrails.common import GuardUnavailable, LazyGuard


class Outcome:
    def __init__(self, passed=True, output="ok", error=""):
        self.validation_passed, self.validated_output, self.error = passed, output, error


class FakeGuard:
    def __init__(self, result):
        self.result = result

    def validate(self, text):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture(autouse=True)
def guards_on(monkeypatch):
    monkeypatch.setattr(settings, "GUARDRAILS_ENABLED", True)


def test_pass_returns_fixed_text():
    assert LazyGuard("t", lambda: FakeGuard(Outcome(output="redacted"))).check("raw").text == "redacted"


def test_validation_error_is_a_failed_result_not_an_exception():
    result = LazyGuard("t", lambda: FakeGuard(ValidationError("toxic"))).check("raw")
    assert not result.passed and "toxic" in result.reason


def test_failed_outcome_is_a_failed_result():
    assert not LazyGuard("t", lambda: FakeGuard(Outcome(passed=False))).check("raw").passed


def test_broken_guard_raises_instead_of_passing():
    def broken():
        raise ImportError("no torch")

    with pytest.raises(GuardUnavailable):
        LazyGuard("t", broken).check("raw")


def test_guard_is_built_once_and_lazily():
    built = []

    def factory():
        built.append(1)
        return FakeGuard(Outcome())

    guard = LazyGuard("t", factory)
    assert built == []
    guard.check("a")
    guard.check("b")
    assert built == [1]


def test_disabled_guardrails_pass_without_building(monkeypatch):
    monkeypatch.setattr(settings, "GUARDRAILS_ENABLED", False)

    def factory():
        raise AssertionError("must not build")

    assert LazyGuard("t", factory).check("raw").passed


class TestTelemetryWarning:
    """Uses the real guardrails settings object, so an upstream rename fails this test loudly."""

    @pytest.fixture
    def rc(self):
        from guardrails.settings import settings as guardrails_settings

        original = guardrails_settings.rc.enable_metrics
        yield guardrails_settings.rc
        guardrails_settings.rc.enable_metrics = original

    def test_warns_when_enabled(self, rc, caplog):
        rc.enable_metrics = True
        with caplog.at_level("WARNING"):
            LazyGuard("t", lambda: FakeGuard(Outcome())).check("x")
        assert "telemetry is ENABLED" in caplog.text

    def test_silent_when_disabled(self, rc, caplog):
        rc.enable_metrics = False
        with caplog.at_level("WARNING"):
            LazyGuard("t", lambda: FakeGuard(Outcome())).check("x")
        assert "telemetry" not in caplog.text
