from contextlib import contextmanager, closing
import http.client
import threading

import pytest
from typer.testing import CliRunner
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest, ExportLogsServiceResponse

from architect.cli.main import app
from architect.otlp import CodexLogServer, MAX_BODY, MAX_RECORDS
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import create_run
from architect.storage.sessions import resolve_session


def export(*names, session='native-thread'):
    request = ExportLogsServiceRequest()
    logs = request.resource_logs.add().scope_logs.add()
    for name in names:
        record = logs.log_records.add(time_unix_nano=1770000000123456789)
        for key, value in {'event.name': name, 'tool_name': 'exec_command',
                           'success': True, 'duration_ms': 12, 'prompt': 'PRIVATE',
                           'unknown': {'secret': 'PRIVATE'},
                           **({'conversation.id': session} if session else {})}.items():
            attr = record.attributes.add(key=key)
            if isinstance(value, bool):
                attr.value.bool_value = value
            elif isinstance(value, int):
                attr.value.int_value = value
            elif isinstance(value, str):
                attr.value.string_value = value
            else:
                attr.value.kvlist_value.values.add(key='secret').value.string_value = 'PRIVATE'
    return request.SerializeToString()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / '.architect/architect.db'
    run = create_run('codex', 'NATIVE', 'OTLP fixture', db_path=db)
    return db, run


@contextmanager
def running(project):
    db, run = project
    with CodexLogServer(('127.0.0.1', 0), run_id=run[:8], db_path=db) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


def post(server, body, path='/v1/logs', headers=None):
    with closing(http.client.HTTPConnection(*server.server_address, timeout=3)) as connection:
        try:
            connection.request('POST', path, body, headers or {'Content-Type': 'application/x-protobuf'})
        except BrokenPipeError:
            # A server may reject headers (e.g. 413) before the upload finishes.
            # Still require the actual HTTP response and status below.
            pass
        response = connection.getresponse()
        return response.status, response.read()


def test_real_binary_http_pipeline(project):
    db, run = project
    with running(project) as server:
        code, body = post(server, export('codex.tool_result', 'unmapped', 'codex.tool_result'))
        assert code == 200
        assert ExportLogsServiceResponse.FromString(body).partial_success.rejected_log_records == 0
        assert (server.recorded, server.ignored) == (2, 1)
    events = FlightRecorder(db).timeline(run)
    assert len(events) == 2
    assert all(e.run_id == run and e.fidelity == 'NATIVE' and e.status == 'success' for e in events)
    assert events[0].metadata['synthetic'] is False
    assert 'PRIVATE' not in events[0].to_json()
    assert resolve_session('codex', 'native-thread', db_path=db) == run
    result = CliRunner().invoke(app, ['inspect', run[:8]])
    assert result.exit_code == 0 and 'TOOL_EXECUTION' in result.stdout


@pytest.mark.parametrize('body,path,headers,expected', [
    (b'\xff', '/v1/logs', None, 400),
    (b'', '/wrong', None, 404),
    (b'{}', '/v1/logs', {'Content-Type': 'application/json'}, 415),
    (b'x' * (MAX_BODY + 1), '/v1/logs', None, 413),
    (b'', '/v1/logs', {'Content-Type': 'application/x-protobuf', 'Content-Encoding': 'gzip'}, 415),
], ids=['malformed', 'route', 'media', 'size', 'encoding'])
def test_invalid_http(project, body, path, headers, expected):
    with running(project) as server:
        assert post(server, body, path, headers)[0] == expected
        assert post(server, export('unknown'))[0] == 200


def test_no_session_uses_listener_run(project):
    with running(project) as server:
        assert post(server, export('codex.tool_result', session=None))[0] == 200
    event, = FlightRecorder(project[0]).timeline(project[1])
    assert 'provider_session_id' not in event.metadata


def test_conflicting_session_partial_rejection(project):
    db, run = project
    with running(project) as server:
        assert post(server, export('codex.tool_result'))[0] == 200
    other = create_run('codex', 'NATIVE', 'other', db_path=db)
    with running((db, other)) as server:
        status, body = post(server, export('codex.tool_result'))
        assert status == 200
        assert ExportLogsServiceResponse.FromString(body).partial_success.rejected_log_records == 1
    assert FlightRecorder(db).timeline(other) == []


@pytest.mark.parametrize('args,exit_code', [
    ([], 2), (['--run', 'missing'], 1),
    (['--run', 'missing', '--port', '70000'], 2),
    (['--run', 'missing', '--host', '0.0.0.0'], 1),
])
def test_cli_arguments(project, args, exit_code):
    result = CliRunner().invoke(app, ['codex-listen', *args])
    assert result.exit_code == exit_code


def test_ctrl_c_closes_server(project, monkeypatch):
    captured = []
    def interrupt(server, **kwargs):
        captured.append(server)
        raise KeyboardInterrupt
    monkeypatch.setattr(CodexLogServer, 'serve_forever', interrupt)
    result = CliRunner().invoke(app, ['codex-listen', '--run', project[1][:8], '--port', '14319'])
    assert result.exit_code == 0 and 'Listener stopped' in result.stdout
    assert captured[0].socket.fileno() == -1


@pytest.mark.parametrize('success,status', [('true', 'success'), ('false', 'failed')])
def test_observed_live_string_attributes(project, success, status):
    request = ExportLogsServiceRequest.FromString(export('codex.tool_result'))
    resource = request.resource_logs[0]
    resource.resource.attributes.add(key='service.name').value.string_value = 'codex_cli_rs'
    record = resource.scope_logs[0].log_records[0]
    for attr in record.attributes:
        if attr.key == 'success':
            attr.value.string_value = success
        elif attr.key == 'duration_ms':
            attr.value.string_value = '53'
    for key in ('arguments', 'output', 'user.email', 'user.account_id', 'authorization'):
        record.attributes.add(key=key).value.string_value = 'PRIVATE'
    with running(project) as server:
        assert post(server, request.SerializeToString())[0] == 200
        assert server.recorded == 1 and server.rejected == 0
    event, = FlightRecorder(project[0]).timeline(project[1])
    assert event.status == status and event.duration_ms == 53
    assert 'PRIVATE' not in event.to_json()


@pytest.mark.parametrize('field,value', [('success', 'unknown'), ('duration_ms', 'nan'),
                                       ('duration_ms', '-1'), ('timestamp', None)])
def test_bad_supported_record_partial_ack(project, field, value):
    request = ExportLogsServiceRequest.FromString(export('codex.tool_result', 'codex.tool_result'))
    record = request.resource_logs[0].scope_logs[0].log_records[0]
    if field == 'timestamp':
        record.time_unix_nano = 0
    else:
        for attr in record.attributes:
            if attr.key == field:
                attr.value.string_value = value
    with running(project) as server:
        code, body = post(server, request.SerializeToString())
        assert code == 200
        assert ExportLogsServiceResponse.FromString(body).partial_success.rejected_log_records == 1
        assert server.recorded == 1


def test_log_record_limit(project):
    with running(project) as server:
        assert post(server, export(*(['unknown'] * (MAX_RECORDS + 1))))[0] == 400
        assert server.recorded == 0


def test_approval_mapping(project):
    request = ExportLogsServiceRequest.FromString(export('codex.tool_decision'))
    request.resource_logs[0].scope_logs[0].log_records[0].attributes.add(key='decision').value.string_value = 'approved'
    with running(project) as server:
        assert post(server, request.SerializeToString())[0] == 200
    event, = FlightRecorder(project[0]).timeline(project[1])
    assert event.event_type == 'approval_requested' and event.status == 'success'
