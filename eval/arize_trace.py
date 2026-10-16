"""Optional Arize tracing for key decision points; a safe no-op without keys.

Only an allow-list of de-identified attributes is ever recorded (ids, categories,
outcome labels, flags). Anything else is silently dropped, so free-text survivor
fields cannot reach a span. Tracing failures never affect the traced code.
"""
import contextlib
import functools
import math
import os

ALLOWED = frozenset({'run_id', 'disaster_id', 'request_id', 'call_id', 'category', 'categories',
                     'outcome', 'status', 'role', 'emergency', 'received', 'lesson_id',
                     'lesson_ids', 'experiment_id', 'case_count', 'organization_id',
                     'proposal_count'})
_MAX_LEN = 80
_tracer = None
_configured = False


def enabled():
    return bool(os.environ.get('ARIZE_API_KEY') and os.environ.get('ARIZE_SPACE_ID'))


def _scalar(value):
    if isinstance(value, bool) or (isinstance(value, (int, float)) and not math.isnan(value)):
        return value
    if isinstance(value, str) and len(value) <= _MAX_LEN:
        return value
    return None


def clean(attrs):
    """Return only allow-listed, short scalar (or list-of-string) attributes."""
    out = {}
    for key, value in attrs.items():
        if key not in ALLOWED or value is None:
            continue
        if isinstance(value, (list, tuple)):
            items = [_scalar(v) for v in value]
            if all(isinstance(v, str) for v in items):
                out['relay.' + key] = items
        elif (kept := _scalar(value)) is not None:
            out['relay.' + key] = kept
    return out


def set_tracer(tracer):
    """Inject a tracer (tests) or None to reset to env-based lazy configuration."""
    global _tracer, _configured
    _tracer, _configured = tracer, tracer is not None


def _get_tracer():
    global _tracer, _configured
    if not _configured:
        _configured = True
        if enabled():
            try:
                from eval.arize import configure_arize
                _tracer = configure_arize().get_tracer('relay.decisions')
            except Exception:  # noqa: BLE001 - tracing must never break the demo
                _tracer = None
    return _tracer


class _Span:
    def __init__(self, name, attrs):
        self.name, self.attrs, self._cm, self._span = name, dict(attrs), None, None

    def set(self, **attrs):
        """Add attributes after the decision is known (filtered the same way)."""
        self.attrs.update(attrs)
        if self._span is not None:
            with contextlib.suppress(Exception):
                for key, value in clean(attrs).items():
                    self._span.set_attribute(key, value)

    def __enter__(self):
        tracer = _get_tracer()
        if tracer is not None:
            try:
                self._cm = tracer.start_as_current_span(self.name)
                self._span = self._cm.__enter__()
                self._span.set_attribute('openinference.span.kind', 'CHAIN')
                for key, value in clean(self.attrs).items():
                    self._span.set_attribute(key, value)
            except Exception:  # noqa: BLE001
                self._cm = self._span = None
        return self

    def __exit__(self, *exc):
        if self._cm is not None:
            with contextlib.suppress(Exception):
                self._cm.__exit__(*exc)
        return False

    def __call__(self, fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with _Span(self.name, self.attrs):
                return fn(*args, **kwargs)
        return wrapper


def traced(name, **attrs):
    """Context manager (yields a span with .set(**attrs)) or decorator."""
    return _Span(name, attrs)
