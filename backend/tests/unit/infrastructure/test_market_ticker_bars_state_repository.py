"""Ticker bars state repository tests."""

from __future__ import annotations

from infrastructure.repositories.market_ticker_bars_state_repository import (
    LAST_ERROR_MESSAGE_MAX_LENGTH,
    _truncate_error_message,
)


def test_truncate_error_message_preserves_short_messages() -> None:
    message = "provider request failed"

    assert _truncate_error_message(message) == message


def test_truncate_error_message_limits_persisted_message_length() -> None:
    message = "x" * (LAST_ERROR_MESSAGE_MAX_LENGTH + 100)

    result = _truncate_error_message(message)

    assert result is not None
    assert len(result) == LAST_ERROR_MESSAGE_MAX_LENGTH
    assert result.endswith("[truncated]")
