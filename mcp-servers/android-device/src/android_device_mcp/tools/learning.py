"""Learning tools for pattern storage and retrieval."""

import logging
from typing import Optional

from ..persistence.learning_store import LearningStore

logger = logging.getLogger(__name__)


async def save_pattern(
    store: LearningStore,
    app_package: str,
    pattern_key: str,
    pattern_type: str,
    pattern_data: dict,
    app_version: Optional[str] = None,
) -> dict:
    """Save a learned pattern.

    Args:
        store: Learning store
        app_package: App package name
        pattern_key: Unique key
        pattern_type: Type (element, flow, strategy, failure)
        pattern_data: Pattern data
        app_version: Optional version

    Returns:
        Save confirmation
    """
    valid_types = {"element", "flow", "strategy", "failure"}
    if pattern_type not in valid_types:
        return {
            "success": False,
            "error": f"Invalid pattern_type. Must be one of: {valid_types}",
        }

    return await store.save_pattern(
        app_package=app_package,
        pattern_key=pattern_key,
        pattern_type=pattern_type,
        pattern_data=pattern_data,
        app_version=app_version,
    )


async def get_pattern(
    store: LearningStore,
    app_package: str,
    pattern_key: str,
) -> Optional[dict]:
    """Retrieve a saved pattern.

    Args:
        store: Learning store
        app_package: App package name
        pattern_key: Pattern key

    Returns:
        Pattern data or None
    """
    return await store.get_pattern(app_package, pattern_key)


async def list_patterns(
    store: LearningStore,
    app_package: str,
    pattern_type: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """List patterns for an app.

    Args:
        store: Learning store
        app_package: App package name
        pattern_type: Optional type filter
        limit: Maximum results

    Returns:
        List of pattern summaries
    """
    return await store.list_patterns(app_package, pattern_type, limit)


async def delete_pattern(
    store: LearningStore,
    app_package: str,
    pattern_key: str,
) -> dict:
    """Delete a pattern.

    Args:
        store: Learning store
        app_package: App package name
        pattern_key: Pattern key

    Returns:
        Deletion result
    """
    return await store.delete_pattern(app_package, pattern_key)


async def log_interaction(
    store: LearningStore,
    app_package: str,
    action_type: str,
    target_selector: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> dict:
    """Log an interaction for reliability tracking.

    Args:
        store: Learning store
        app_package: App package name
        action_type: Type of action
        target_selector: Selector used
        success: Whether successful
        error_message: Error if failed
        latency_ms: Action latency

    Returns:
        Log confirmation
    """
    return await store.log_interaction(
        app_package=app_package,
        action_type=action_type,
        target_selector=target_selector,
        success=success,
        error_message=error_message,
        latency_ms=latency_ms,
    )


async def get_stats(
    store: LearningStore,
    app_package: str,
    days: int = 30,
) -> dict:
    """Get reliability statistics.

    Args:
        store: Learning store
        app_package: App package name
        days: Days to analyze

    Returns:
        Success rates by action type
    """
    return await store.get_reliability_stats(app_package, days)
