"""Utility functions for the Android Device MCP server."""

import asyncio
import functools
import logging
from typing import Callable, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    delay_ms: int = 500,
    backoff: float = 1.5,
    exceptions: tuple = (Exception,),
    **kwargs: Any,
) -> Any:
    """Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Arguments to pass to function
        max_retries: Maximum number of retry attempts
        delay_ms: Initial delay between retries in milliseconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch and retry
        **kwargs: Keyword arguments to pass to function

    Returns:
        Result of the function

    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    current_delay = delay_ms

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            if attempt < max_retries:
                logger.debug(
                    f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                    f"after {current_delay}ms: {e}"
                )
                await asyncio.sleep(current_delay / 1000.0)
                current_delay = int(current_delay * backoff)
            else:
                logger.warning(
                    f"All {max_retries} retries failed for {func.__name__}: {e}"
                )

    raise last_exception  # type: ignore


def with_retry(
    max_retries: int = 3,
    delay_ms: int = 500,
    backoff: float = 1.5,
    exceptions: tuple = (Exception,),
):
    """Decorator to add retry logic to an async function.

    Args:
        max_retries: Maximum number of retry attempts
        delay_ms: Initial delay between retries in milliseconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch and retry

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_async(
                func,
                *args,
                max_retries=max_retries,
                delay_ms=delay_ms,
                backoff=backoff,
                exceptions=exceptions,
                **kwargs,
            )
        return wrapper
    return decorator


class RetryError(Exception):
    """Error raised when all retry attempts fail."""

    def __init__(self, message: str, attempts: int, last_error: Exception):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


def format_error_message(error: Exception, context: str = "") -> str:
    """Format an error message with context for user-friendly display.

    Args:
        error: The exception that occurred
        context: Additional context about what was being attempted

    Returns:
        Formatted error message string
    """
    error_type = type(error).__name__
    error_msg = str(error)

    if context:
        return f"{context}: {error_type} - {error_msg}"
    return f"{error_type}: {error_msg}"


def safe_dict_get(d: dict, *keys: str, default: Any = None) -> Any:
    """Safely get nested dictionary values.

    Args:
        d: Dictionary to search
        *keys: Sequence of keys to traverse
        default: Default value if key not found

    Returns:
        Value at nested key path, or default
    """
    current = d
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current
