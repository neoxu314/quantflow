"""Tests for alerts module."""

import pytest
import logging
import io
import re
from datetime import datetime

from quantflow.execution.alerts.base import AlertMessage, AlertChannel, LogAlertChannel


class TestAlertMessage:
    def test_defaults(self):
        msg = AlertMessage(title="Test Alert", content="Details here")
        assert msg.title == "Test Alert"
        assert msg.content == "Details here"
        assert msg.level == "info"
        assert msg.timestamp is None

    def test_custom_level(self):
        msg = AlertMessage(title="Critical", content="System down", level="error")
        assert msg.level == "error"

    def test_timestamp(self):
        ts = datetime.now().isoformat()
        msg = AlertMessage(title="TS", content="...", timestamp=ts)
        assert msg.timestamp == ts

    def test_format_content_info(self):
        msg = AlertMessage(title="Price Alert", content="NVDA crossed 500", level="info")
        formatted = msg.format_content()
        assert "[info]" in formatted
        assert "Price Alert" in formatted
        assert "NVDA crossed 500" in formatted


class TestLogAlertChannel:
    def test_get_name(self):
        ch = LogAlertChannel()
        assert ch.get_name() == "Log"

    def test_send_returns_true(self, caplog):
        ch = LogAlertChannel()
        msg = AlertMessage(title="Test", content="Alert body", level="info")
        result = ch.send(msg)
        assert result is True

    def test_send_logs_at_configured_level(self, caplog):
        ch = LogAlertChannel(level="WARNING")
        msg = AlertMessage(title="Warn Test", content="Something wrong")
        ch.send(msg)

        assert any("Warn Test" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)

    def test_custom_log_level(self):
        ch = LogAlertChannel(level="ERROR")
        assert ch.level == "ERROR"

    def test_send_format_includes_title_and_content(self, caplog):
        ch = LogAlertChannel()
        msg = AlertMessage(title="MyAlert", content="detail_xyz")
        with caplog.at_level(logging.INFO, logger="quantflow.execution.alerts.base"):
            ch.send(msg)

        # The log should contain both title and content
        combined = " ".join(record.message for record in caplog.records)
        assert "MyAlert" in combined
        assert "detail_xyz" in combined
