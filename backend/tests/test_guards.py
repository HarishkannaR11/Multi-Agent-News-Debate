import pytest  # the test framework
from guardrails.errors import ValidationError  # the error the Guardrails library raises when text fails a check

from backend.config import settings  # the settings object (the guardrails on/off switch lives here)
from backend.graph.guardrails.common import GuardUnavailable, LazyGuard  # the wrapper under test and its error


# A fake validation result with the same three fields the real library result has.
class Outcome:
    def __init__(self, passed=True, output="ok", error=""):
        # Assign all three attributes at once.
        self.validation_passed, self.validated_output, self.error = passed, output, error


# A fake guard: returns the result it was given, or raises it if it is an exception.
class FakeGuard:
    def __init__(self, result):
        self.result = result

    def validate(self, text):
        # An exception means "simulate a failed check".
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


# autouse=True: turn the guardrails ON for every test in this file (the global test setup turns them off).
@pytest.fixture(autouse=True)
def guards_on(monkeypatch):
    monkeypatch.setattr(settings, "GUARDRAILS_ENABLED", True)


# A passing check returns the guard's possibly-fixed text (e.g. with personal data redacted).
def test_pass_returns_fixed_text():
    assert LazyGuard("t", lambda: FakeGuard(Outcome(output="redacted"))).check("raw").text == "redacted"


# When the library raises a validation error, the wrapper turns it into a normal "failed" result.
def test_validation_error_is_a_failed_result_not_an_exception():
    result = LazyGuard("t", lambda: FakeGuard(ValidationError("toxic"))).check("raw")
    assert not result.passed and "toxic" in result.reason


# A result that says validation did not pass is also a failed result.
def test_failed_outcome_is_a_failed_result():
    assert not LazyGuard("t", lambda: FakeGuard(Outcome(passed=False))).check("raw").passed


# If the guard cannot even be built (e.g. a missing library), the check must raise - never silently pass.
def test_broken_guard_raises_instead_of_passing():
    def broken():
        raise ImportError("no torch")

    with pytest.raises(GuardUnavailable):
        LazyGuard("t", broken).check("raw")


# The (expensive) guard is built only on first use and then reused.
def test_guard_is_built_once_and_lazily():
    # Each time the factory runs, it adds a 1 here.
    built = []

    def factory():
        built.append(1)
        return FakeGuard(Outcome())

    guard = LazyGuard("t", factory)
    # Creating the wrapper must not build the guard yet.
    assert built == []
    guard.check("a")
    guard.check("b")
    # Two checks, but only one build.
    assert built == [1]


# With the guardrails switched off, text passes and the guard is never even built.
def test_disabled_guardrails_pass_without_building(monkeypatch):
    monkeypatch.setattr(settings, "GUARDRAILS_ENABLED", False)

    def factory():
        raise AssertionError("must not build")

    assert LazyGuard("t", factory).check("raw").passed


# Tests for the warning shown when the library's usage reporting (telemetry) is switched on.
class TestTelemetryWarning:
    """Uses the real guardrails settings object, so an upstream rename fails this test loudly."""

    # A fixture that hands the test the library's real config object and restores its setting afterwards.
    @pytest.fixture
    def rc(self):
        from guardrails.settings import settings as guardrails_settings

        # Remember the current value.
        original = guardrails_settings.rc.enable_metrics
        yield guardrails_settings.rc
        # After the test, put it back.
        guardrails_settings.rc.enable_metrics = original

    # With telemetry on, a warning must be logged.
    def test_warns_when_enabled(self, rc, caplog):
        rc.enable_metrics = True
        # caplog captures log messages at WARNING level and above.
        with caplog.at_level("WARNING"):
            LazyGuard("t", lambda: FakeGuard(Outcome())).check("x")
        assert "telemetry is ENABLED" in caplog.text

    # With telemetry off, no warning about it appears.
    def test_silent_when_disabled(self, rc, caplog):
        rc.enable_metrics = False
        with caplog.at_level("WARNING"):
            LazyGuard("t", lambda: FakeGuard(Outcome())).check("x")
        assert "telemetry" not in caplog.text
