import functools
import logging
import re
import sys
from app.core.config import settings

_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)([?&](?:[a-z0-9._-]*[_-])?"
    r"(?:api[_-]?key|subscription[_-]?key|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|refresh[_-]?token|id[_-]?token|apikey|key|token|auth|"
    r"secret|pwd|passwd|password|credential|signature|sig|bearer)"
    r"(?:[_-][a-z0-9._-]*)?=)(?!\[REDACTED\])[^&\s\"'<>\)\}\]]+"
)
_SENSITIVE_URLENCODED_QUERY_RE = re.compile(
    r"(?i)((?:%3f|%26)(?:[a-z0-9._-]*[_-])?"
    r"(?:api[_-]?key|subscription[_-]?key|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|refresh[_-]?token|id[_-]?token|apikey|key|token|auth|"
    r"secret|pwd|passwd|password|credential|signature|sig|bearer)"
    r"(?:[_-][a-z0-9._-]*)?%3d)(?!\[REDACTED\])(?:(?!%26)[^\s&\"'<>\)\}\]])+"
)
_SENSITIVE_URL_USERINFO_RE = re.compile(r"(?i)(https?://)(?!\[REDACTED\]@)[^\s/@]+@")
_SENSITIVE_URLENCODED_USERINFO_RE = re.compile(r"(?i)(https?%3a%2f%2f)(?!\[REDACTED\]%40)[^\s/%]+%40")

_KV_SENSITIVE_KEYS = (
    r"(?:authorization|proxy-authorization|x-api-key|x-auth-token|x-internal-key|"
    r"x-elevated-key|x-subscription-key|ocp-apim-subscription-key|subscription-key|"
    r"api[-_]?key|access[-_]?token|auth[-_]?token|client[-_]?secret|refresh[-_]?token|"
    r"apikey|token|secret|password|passwd|pwd)"
)
_SENSITIVE_QUOTED_KV_RE = re.compile(
    rf"(?i)(['\"]?{_KV_SENSITIVE_KEYS}['\"]?\s*[:=]\s*)(['\"])(?!\[REDACTED\]\2)(?:(?!(?<!\\)\2)[^\r\n])+\2"
)
_SENSITIVE_UNQUOTED_KV_RE = re.compile(
    rf"(?i)(['\"]?{_KV_SENSITIVE_KEYS}['\"]?\s*[:=]\s*)"
    r"(?:(?:bearer|basic)\s+)?(?!\[REDACTED\])[^\s,;'\")\}\]]+"
)
_SENSITIVE_BYTES_TUPLE_RE = re.compile(
    rf"(?i)(b['\"]{_KV_SENSITIVE_KEYS}['\"]\s*,\s*)b['\"][^'\"]+['\"]"
)
_SENSITIVE_STANDALONE_BEARER_RE = re.compile(
    r"(?i)\b(bearer)\s+(?!\[REDACTED\])"
    r"(?!token\b|auth(?:entication)?\b|scheme\b|credentials?\b|header\b|"
    r"required\b|missing\b|expired\b|invalid\b|decode\b|claims?\b|signature\b|"
    r"mode\b|validation\b|verification\b|support\b|usage\b|format\b|prefix\b|type\b)"
    r"([^\s,;'\")\}\]]{3,})"
)
_SENSITIVE_STANDALONE_BASIC_RE = re.compile(
    r"(?i)\b(basic)\s+(?!\[REDACTED\])"
    r"(?!auth(?:entication)?\b|scheme\b|credentials?\b|header\b|"
    r"required\b|missing\b|routing\b|fallback\b|mode\b|checks?\b|tests?\b|info\b|setup\b)"
    r"(?=(?:[A-Za-z0-9+/]{8,}={0,2}\b|[^\s]*[0-9_=:/+-][^\s]*))"
    r"([^\s,;'\")\}\]]{6,})"
)
_SENSITIVE_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")


def sanitize_sensitive_log_text(text: str | None) -> str:
    """Redacts URL credentials, query secrets, JSON/header tokens, Bearer/Basic auth, and JWTs."""
    if not text:
        return ""
    cleaned = _SENSITIVE_URL_USERINFO_RE.sub(r"\1[REDACTED]@", text)
    cleaned = _SENSITIVE_URLENCODED_USERINFO_RE.sub(r"\1[REDACTED]%40", cleaned)
    cleaned = _SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", cleaned)
    cleaned = _SENSITIVE_URLENCODED_QUERY_RE.sub(r"\1[REDACTED]", cleaned)
    cleaned = _SENSITIVE_BYTES_TUPLE_RE.sub(r"\1b'[REDACTED]'", cleaned)
    cleaned = _SENSITIVE_QUOTED_KV_RE.sub(r"\1\2[REDACTED]\2", cleaned)
    cleaned = _SENSITIVE_UNQUOTED_KV_RE.sub(r"\1[REDACTED]", cleaned)
    cleaned = _SENSITIVE_STANDALONE_BEARER_RE.sub(r"\1 [REDACTED]", cleaned)
    cleaned = _SENSITIVE_STANDALONE_BASIC_RE.sub(r"\1 [REDACTED]", cleaned)
    cleaned = _SENSITIVE_JWT_RE.sub("[REDACTED]", cleaned)
    return cleaned


class SensitiveDataRedactionFilter(logging.Filter):
    """Defense-in-depth logging filter stripping credentials from formatted log messages and tracebacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            sanitized = sanitize_sensitive_log_text(rendered)
            if sanitized != rendered:
                record.msg = sanitized
                record.args = ()
            if record.exc_info and not record.exc_text:
                formatted_exc = logging._defaultFormatter.formatException(record.exc_info)
                sanitized_exc = sanitize_sensitive_log_text(formatted_exc)
                if sanitized_exc != formatted_exc:
                    record.exc_text = sanitized_exc
        except Exception:
            if isinstance(record.msg, str):
                record.msg = sanitize_sensitive_log_text(record.msg)
        return True


_REDACTION_FILTER = SensitiveDataRedactionFilter()
_DEFAULT_RECORD_FACTORY = logging.getLogRecordFactory()
_ORIGINAL_ADD_HANDLER = logging.Logger.addHandler
_LOGGING_HOOKS_INSTALLED = False


def _redacting_log_record_factory(*args, **kwargs) -> logging.LogRecord:
    record = _DEFAULT_RECORD_FACTORY(*args, **kwargs)
    _REDACTION_FILTER.filter(record)
    return record


setattr(_redacting_log_record_factory, "_kognisync_redacting_factory", True)


def _install_global_redaction_hooks() -> None:
    """
    Ensures every LogRecord constructed and every Handler attached (including post-init
    custom loggers/handlers or third-party transport loggers) enforces credential redaction
    idempotently without duplicate filter instances.
    """
    global _LOGGING_HOOKS_INSTALLED, _DEFAULT_RECORD_FACTORY

    current_factory = logging.getLogRecordFactory()
    if not getattr(current_factory, "_kognisync_redacting_factory", False):
        _DEFAULT_RECORD_FACTORY = current_factory
        logging.setLogRecordFactory(_redacting_log_record_factory)

    if not getattr(logging.Logger.addHandler, "_kognisync_redaction_wrapped", False):
        orig_add_handler = _ORIGINAL_ADD_HANDLER

        @functools.wraps(orig_add_handler)
        def _wrapped_add_handler(self: logging.Logger, hdlr: logging.Handler) -> None:
            _attach_redaction_filter_to_handler(hdlr)
            orig_add_handler(self, hdlr)

        setattr(_wrapped_add_handler, "_kognisync_redaction_wrapped", True)
        logging.Logger.addHandler = _wrapped_add_handler  # type: ignore[method-assign]

    _LOGGING_HOOKS_INSTALLED = True


def _attach_redaction_filter(target_logger: logging.Logger) -> None:
    if not any(isinstance(f, SensitiveDataRedactionFilter) for f in target_logger.filters):
        target_logger.addFilter(_REDACTION_FILTER)


def _attach_redaction_filter_to_handler(handler: logging.Handler) -> None:
    if not any(isinstance(f, SensitiveDataRedactionFilter) for f in handler.filters):
        handler.addFilter(_REDACTION_FILTER)


def harden_http_client_logging() -> None:
    """
    Suppresses noisy INFO/DEBUG HTTP transport request logs (`httpx`/`httpcore` including HTTP/2)
    and installs global idempotent LogRecord + handler redaction across transport, access, and app loggers.
    """
    _install_global_redaction_hooks()

    for transport_logger_name in (
        "httpx",
        "httpcore",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.connection",
    ):
        transport_logger = logging.getLogger(transport_logger_name)
        transport_logger.setLevel(logging.WARNING)
        _attach_redaction_filter(transport_logger)
        for handler in transport_logger.handlers:
            _attach_redaction_filter_to_handler(handler)

    for app_logger_name in ("", "kognisync", "uvicorn.access", "uvicorn.error"):
        target = logging.getLogger(app_logger_name)
        _attach_redaction_filter(target)
        for handler in target.handlers:
            _attach_redaction_filter_to_handler(handler)

    # Also ensure any already-instantiated loggers/handlers in loggerDict are covered
    for candidate in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(candidate, logging.Logger):
            _attach_redaction_filter(candidate)
            for handler in candidate.handlers:
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
