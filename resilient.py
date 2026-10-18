"""Retry and back-off for the Gemini model.

Wrap the model once (see llm_utils.py) and every existing llm.invoke(...)
call in the project gets automatic retries on rate-limit / overload errors.
"""
import random
import time

_RETRY_WORDS = (
    "429", "resource_exhausted", "rate limit", "quota",
    "503", "unavailable", "overloaded", "deadline", "timed out", "timeout",
)
_RETRY_CODES = (429, 500, 502, 503, 504)


class LLMBusyError(Exception):
    """The AI service stayed busy (or out of quota) after several tries."""


def is_retryable(err):
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if isinstance(code, int) and code in _RETRY_CODES:
        return True
    msg = str(err).lower()
    return any(word in msg for word in _RETRY_WORDS)


def call_with_retry(fn, *args, retries=3, base_delay=2.0, **kwargs):
    """Call fn; on a retryable error wait 2s, 4s, 8s (plus jitter) and retry."""
    last = None
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last = e
            if not is_retryable(e) or attempt == retries:
                break
            time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))
    if is_retryable(last):
        raise LLMBusyError(
            "The AI service is busy or the free quota is used up. "
            "Please wait a minute and try again."
        ) from last
    raise last


class RetryingLLM:
    """Looks like the normal LangChain model but retries on temporary errors."""

    def __init__(self, inner, retries=3, base_delay=2.0):
        self._inner = inner
        self._retries = retries
        self._base_delay = base_delay

    def invoke(self, *args, **kwargs):
        return call_with_retry(
            self._inner.invoke, *args,
            retries=self._retries, base_delay=self._base_delay, **kwargs
        )

    def bind_tools(self, *args, **kwargs):
        return RetryingLLM(
            self._inner.bind_tools(*args, **kwargs),
            self._retries, self._base_delay,
        )

    def __getattr__(self, name):
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)


def wrap_llm(llm, retries=3, base_delay=2.0):
    return RetryingLLM(llm, retries, base_delay)