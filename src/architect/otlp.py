"""Foreground, loopback-only binary OTLP logs transport for Codex."""

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import socket
import sqlite3

from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest, ExportLogsServiceResponse,
)

from architect.observers.codex import CODEX_EVENT_NAMES, CodexObserver
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import get_run
from architect.storage.sessions import bind_session

MAX_BODY = 1024 * 1024
MAX_RECORDS = 2048


def _attributes(values):
    result = {}
    for pair in values:
        kind = pair.value.WhichOneof("value")
        if kind in {"string_value", "bool_value", "int_value", "double_value"}:
            if pair.key in result:
                raise ValueError("Duplicate OTLP attribute")
            result[pair.key] = getattr(pair.value, kind)
    return result


def decode_logs(body: bytes) -> list[dict]:
    """Decode protobuf envelopes; domain mapping stays in CodexObserver."""
    request = ExportLogsServiceRequest()
    request.ParseFromString(body)
    records = []
    for resource in request.resource_logs:
        resource_attributes = _attributes(resource.resource.attributes)
        for scope in resource.scope_logs:
            for log in scope.log_records:
                if len(records) >= MAX_RECORDS:
                    raise ValueError("Too many log records")
                attributes = resource_attributes | _attributes(log.attributes)
                name = attributes.get("event.name", getattr(log, "event_name", "") or log.body.string_value)
                nanos = log.time_unix_nano or log.observed_time_unix_nano
                timestamp = (datetime(1970, 1, 1, tzinfo=timezone.utc)
                             + timedelta(microseconds=nanos // 1000)).isoformat() if nanos else None
                records.append({"event_name": name, "timestamp": timestamp,
                                "attributes": attributes})
    return records


class CodexLogServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], *, run_id: str, db_path: str | Path):
        if address[0] != "127.0.0.1":
            raise ValueError("Only loopback host 127.0.0.1 is supported")
        if not 0 <= address[1] <= 65535:
            raise ValueError("Invalid port")
        self.database = Path(db_path).resolve()
        if not self.database.is_file():
            raise ValueError("Project database missing; run architect init first")
        run = get_run(run_id, db_path=self.database)
        if run is None:
            raise ValueError("Unknown run")
        self.run_id = run["run_id"]
        self.recorder = FlightRecorder(self.database)
        self.observer = CodexObserver(live=True)
        self.recorded = self.ignored = self.rejected = 0
        super().__init__(address, _Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address

    def ingest_logs(self, records: list[dict]) -> bytes:
        response = ExportLogsServiceResponse()
        rejected = 0
        for record in records:
            if record["event_name"] not in CODEX_EVENT_NAMES:
                self.ignored += 1
                continue
            try:
                events = self.observer.normalize(record, run_id=self.run_id)
                session = record["attributes"].get("conversation.id")
                if session is not None:
                    bind_session("codex", session, self.run_id, db_path=self.database)
                for event in events:
                    self.recorder.record(event)
                    self.recorded += 1
            except (ValueError, TypeError):
                rejected += 1
        self.rejected += rejected
        if rejected:
            response.partial_success.rejected_log_records = rejected
            response.partial_success.error_message = "Unsupported Codex fields or conflicting session binding"
        return response.SerializeToString()


class _Handler(BaseHTTPRequestHandler):
    server: CodexLogServer

    def log_message(self, *args):
        pass  # Do not echo raw paths or telemetry into terminal logs.

    def _reply(self, status: int, body: bytes = b"", content_type="application/x-protobuf"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        self._reply(405)

    def do_POST(self):
        if self.path != "/v1/logs":
            self._reply(404)
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/x-protobuf":
            self._reply(415)
            return
        if self.headers.get("Content-Encoding", "identity") != "identity" or self.headers.get("Transfer-Encoding"):
            self._reply(415)
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            self._reply(411)
            return
        if len(lengths[0]) > 10:
            self._reply(413)
            return
        length = int(lengths[0])
        if length > MAX_BODY:
            self._reply(413)
            return
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                self._reply(400)
                return
            records = decode_logs(body)
            response = self.server.ingest_logs(records)
        except (DecodeError, ValueError, OverflowError):
            self._reply(400)
        except (TimeoutError, socket.timeout):
            self._reply(408)
        except sqlite3.Error:
            self._reply(503)
        else:
            self._reply(200, response)
