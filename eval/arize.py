"""Explicit opt-in Arize AX/OpenTelemetry export of aggregate demo evaluation.

No reports, phone numbers, survivor IDs, labels, or decision payloads are exported.
The optional SDK is imported only when configure_arize is explicitly called.
"""

import os


def configure_arize(*, register=None, transport=None):
    """Return a configured provider; call only after opting into external tracing."""
    space = os.environ.get('ARIZE_SPACE_ID')
    key = os.environ.get('ARIZE_API_KEY')
    if not space or not key:
        raise ValueError('ARIZE_SPACE_ID and ARIZE_API_KEY are required')
    if register is None:
        from arize.otel import Transport, register
        transport = Transport.HTTP
    return register(space_id=space, api_key=key,
                    project_name=os.environ.get('ARIZE_PROJECT_NAME') or 'relay-demo',
                    endpoint='https://otlp.arize.com/v1/traces', transport=transport,
                    set_global_tracer_provider=False, verbose=False)


def trace_comparison(provider, result):
    """Export aggregate results and flush; errors remain visible to the caller.

    A successful local flush does not supply a hosted trace URL or prove ingestion.
    """
    tracer = provider.get_tracer('relay.recovery.evaluation')
    with tracer.start_as_current_span('relay.recovery.comparison') as span:
        span.set_attribute('openinference.span.kind', 'EVALUATOR')
        span.set_attribute('relay.experiment_id', result['experiment_id'])
        span.set_attribute('relay.case_count', result['case_count'])
        span.set_attribute('relay.measurement_type', result['measurement_type'])
        for variant in ('without_history', 'with_history'):
            for name, value in result[variant].items():
                if value is not None:
                    span.set_attribute(f'relay.{variant}.{name}', value)
    if not provider.force_flush():
        raise RuntimeError('Arize trace exporter did not flush successfully')
