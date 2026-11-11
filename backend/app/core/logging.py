import logging
import re
import sys
from app.core.config import settings

_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)([?&](?:api_?key|access_token|key|token|auth|secret|pwd|password|credential|signature|sig)=)[^&\s\"'<>\)]+"
)
_SENSITIVE_AUTH_HEADER_RE = re.compile(
    r"(?i)((?:authorization|x-api-key|x-auth-token|x-internal-key|x-elevated-key|apikey|token)\s*[:=]\s*)(?:bearer\s+|basic\s+)?(['\"]?)[^\s,'\";\)]+\2"
)
_SENSITIVE_BYTES_TUPLE_RE = re.compile(
    r"(?i)(b['\"](?:authorization|x-api-key|x-auth-token|x-internal-key|x-elevated-key|apikey|token)['\"]\s*,\s*)b['\"][^'\"]+['\"]"
)
_SENSITIVE_URL_USERINFO_RE = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")


def sanitize_sensitive_log_text(text: str | None) -> str:
    """Redacts URL query secrets, userinfo credentials, and auth header tokens from log strings."""
    if not text:
        return ""
    cleaned = _SENSITIVE_URL_USERINFO_RE.sub(r"\1[REDACTED]@", text)
    cleaned = _SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", cleaned)
    cleaned = _SENSITIVE_AUTH_HEADER_RE.sub(r"\1[REDACTED]", cleaned)
    cleaned = _SENSITIVE_BYTES_TUPLE_RE.sub(r"\1b'[REDACTED]'", cleaned)
    return cleaned


class SensitiveDataRedactionFilter(logging.Filter):
    """Defense-in-depth logging filter stripping credentials from formatted log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            sanitized = sanitize_sensitive_log_text(rendered)
            if sanitized != rendered:
                record.msg = sanitized
                record.args = ()
        except Exception:
            if isinstance(record.msg, str):
                record.msg = sanitize_sensitive_log_text(record.msg)
        return True


_REDACTION_FILTER = SensitiveDataRedactionFilter()


def _attach_redaction_filter(target_logger: logging.Logger) -> None:
    if not any(isinstance(f, SensitiveDataRedactionFilter) for f in target_logger.filters):
        target_logger.addFilter(_REDACTION_FILTER)


def _attach_redaction_filter_to_handler(handler: logging.Handler) -> None:
    if not any(isinstance(f, SensitiveDataRedactionFilter) for f in handler.filters):
        handler.addFilter(_REDACTION_FILTER)


def harden_http_client_logging() -> None:
    """
    Suppresses noisy INFO/DEBUG HTTP transport request logs (`httpx`/`httpcore`) that would
    otherwise emit raw URLs containing query credentials, and applies defense-in-depth
    redaction filters across transport, access, and application loggers.
    """
    for transport_logger_name in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection"):
        transport_logger = logging.getLogger(transport_logger_name)
        transport_logger.setLevel(logging.WARNING)
        _attach_redaction_filter(transport_logger)

    for app_logger_name in ("", "kognisync", "uvicorn.access", "uvicorn.error"):
        target = logging.getLogger(app_logger_name)
        _attach_redaction_filter(target)
        for handler in target.handlers:
            _attach_redaction_filter_to_handler(handler)


def setup_logging():
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    stream_handler = logging.StreamHandler(sys.stdout)
    _attach_redaction_filter_to_handler(stream_handler)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[stream_handler],
    )
    logging.getLogger("uvicorn.access").setLevel(log_level)
    harden_http_client_logging()


harden_http_client_logging()
logger = logging.getLogger("kognisync")
