import logging
import time
from collections.abc import Callable

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout

logger = logging.getLogger(__name__)


def invoke_with_rate_limit_retry[T](
    invoke: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 10.0,
) -> T:
    """Retry temporary connection and timeout failures."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    if base_delay < 0 or max_delay < 0:
        raise ValueError("Retry delays cannot be negative")

    for attempt in range(max_attempts):
        try:
            return invoke()

        except (RequestsConnectionError, Timeout):
            if attempt == max_attempts - 1:
                logger.warning(
                    "LLM connection failed after %s attempts.",
                    max_attempts,
                )
                raise

            delay = min(base_delay * (2**attempt), max_delay)

            logger.warning(
                "LLM connection failed; retrying in %.1f seconds "
                "(attempt %s/%s).",
                delay,
                attempt + 1,
                max_attempts,
            )
            time.sleep(delay)

    raise RuntimeError("LLM invocation failed unexpectedly")


            