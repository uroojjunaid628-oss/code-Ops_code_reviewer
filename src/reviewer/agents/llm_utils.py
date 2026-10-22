import logging
import time
from collections.abc import Callable

from groq import RateLimitError

logger = logging.getLogger(__name__)


def invoke_with_rate_limit_retry[T](
    invoke: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 5.0,
    max_delay: float = 30.0,
) -> T:
    """Retry rate-limited LLM calls with bounded exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return invoke()
        except RateLimitError as exc:
            if attempt == max_attempts - 1:
                logger.warning(
                    "LLM rate limit persists after %s attempts.",
                    max_attempts,
                )
                raise

            delay = min(base_delay * (2**attempt), max_delay)

            # Prefer provider-supplied retry timing when available.
            retry_after = getattr(exc, "retry_after", None)
            response = getattr(exc, "response", None)

            if retry_after is None and response is not None:
                headers = getattr(response, "headers", {})
                retry_after = headers.get("retry-after")

            try:
                if retry_after is not None:
                    delay = min(max(float(retry_after), 0.0), max_delay)
            except (TypeError, ValueError):
                pass

            logger.warning(
                "LLM rate limit reached; retrying in %.1f seconds "
                "(attempt %s/%s).",
                delay,
                attempt + 1,
                max_attempts,
            )
            time.sleep(delay)

    raise RuntimeError("LLM invocation failed unexpectedly")
