"""Interaction tools for taps, swipes, typing, and gestures."""

import logging
from typing import Optional

from ..adapters.adb import ADBAdapter, ADBError
from ..adapters.uiautomator import UIAutomatorAdapter
from ..persistence.learning_store import LearningStore

logger = logging.getLogger(__name__)


async def perform_tap(adb: ADBAdapter, x: int, y: int) -> dict:
    """Tap at specific coordinates.

    Args:
        adb: ADB adapter
        x: X coordinate
        y: Y coordinate

    Returns:
        Success status
    """
    try:
        result = await adb.tap(x, y)
        return {
            "success": result.success,
            "x": x,
            "y": y,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_tap_element(
    adb: ADBAdapter,
    uia: UIAutomatorAdapter,
    learning: LearningStore,
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    content_desc: Optional[str] = None,
    xpath: Optional[str] = None,
    index: int = 0,
) -> dict:
    """Tap on a UI element.

    Args:
        adb: ADB adapter
        uia: UIAutomator adapter
        learning: Learning store
        text: Match by text
        resource_id: Match by resource ID
        content_desc: Match by content description
        xpath: XPath selector
        index: Index if multiple matches

    Returns:
        Success status with element info
    """
    try:
        # Find elements
        elements = await uia.find_elements(
            text=text,
            resource_id=resource_id,
            content_desc=content_desc,
            xpath=xpath,
            limit=index + 1,
        )

        if not elements:
            selector = text or resource_id or content_desc or xpath
            return {
                "success": False,
                "error": f"Element not found: {selector}",
                "selector": selector,
            }

        if index >= len(elements):
            return {
                "success": False,
                "error": f"Index {index} out of range, found {len(elements)} elements",
            }

        element = elements[index]
        x, y = element.center

        # Perform tap
        result = await adb.tap(x, y)

        # Log interaction
        if learning:
            try:
                pkg = await adb.get_current_package()
                await learning.log_interaction(
                    app_package=pkg,
                    action_type="tap_element",
                    target_selector=resource_id or text or content_desc,
                    success=result.success,
                )
            except Exception as e:
                logger.debug(f"Failed to log interaction: {e}")

        return {
            "success": result.success,
            "element": element.to_dict(),
            "tapped_at": {"x": x, "y": y},
            "error": result.stderr if not result.success else None,
        }

    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_double_tap(adb: ADBAdapter, x: int, y: int) -> dict:
    """Double tap at coordinates.

    Args:
        adb: ADB adapter
        x: X coordinate
        y: Y coordinate

    Returns:
        Success status
    """
    try:
        result = await adb.double_tap(x, y)
        return {
            "success": result.success,
            "x": x,
            "y": y,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_long_press(adb: ADBAdapter, x: int, y: int, duration_ms: int) -> dict:
    """Long press at coordinates.

    Args:
        adb: ADB adapter
        x: X coordinate
        y: Y coordinate
        duration_ms: Press duration

    Returns:
        Success status
    """
    try:
        result = await adb.long_press(x, y, duration_ms)
        return {
            "success": result.success,
            "x": x,
            "y": y,
            "duration_ms": duration_ms,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_swipe(
    adb: ADBAdapter,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int,
) -> dict:
    """Swipe from one point to another.

    Args:
        adb: ADB adapter
        start_x: Starting X
        start_y: Starting Y
        end_x: Ending X
        end_y: Ending Y
        duration_ms: Swipe duration

    Returns:
        Success status
    """
    try:
        result = await adb.swipe(start_x, start_y, end_x, end_y, duration_ms)
        return {
            "success": result.success,
            "start": {"x": start_x, "y": start_y},
            "end": {"x": end_x, "y": end_y},
            "duration_ms": duration_ms,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_scroll(adb: ADBAdapter, direction: str, amount: float) -> dict:
    """Scroll the screen.

    Args:
        adb: ADB adapter
        direction: 'up', 'down', 'left', 'right'
        amount: Scroll amount (0.0-1.0)

    Returns:
        Success status
    """
    try:
        screen = await adb.get_screen_size()
        width, height = screen["width"], screen["height"]

        # Calculate scroll coordinates
        center_x = width // 2
        center_y = height // 2
        scroll_dist_x = int(width * amount * 0.8)
        scroll_dist_y = int(height * amount * 0.8)

        if direction == "up":
            start_x, start_y = center_x, center_y + scroll_dist_y // 2
            end_x, end_y = center_x, center_y - scroll_dist_y // 2
        elif direction == "down":
            start_x, start_y = center_x, center_y - scroll_dist_y // 2
            end_x, end_y = center_x, center_y + scroll_dist_y // 2
        elif direction == "left":
            start_x, start_y = center_x + scroll_dist_x // 2, center_y
            end_x, end_y = center_x - scroll_dist_x // 2, center_y
        elif direction == "right":
            start_x, start_y = center_x - scroll_dist_x // 2, center_y
            end_x, end_y = center_x + scroll_dist_x // 2, center_y
        else:
            return {"success": False, "error": f"Invalid direction: {direction}"}

        result = await adb.swipe(start_x, start_y, end_x, end_y, 300)
        return {
            "success": result.success,
            "direction": direction,
            "amount": amount,
            "error": result.stderr if not result.success else None,
        }

    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_pinch(
    uia: UIAutomatorAdapter,
    center_x: int,
    center_y: int,
    zoom_in: bool,
    scale: float,
) -> dict:
    """Pinch zoom gesture.

    Args:
        uia: UIAutomator adapter
        center_x: Center X
        center_y: Center Y
        zoom_in: True to zoom in
        scale: Scale factor

    Returns:
        Success status
    """
    try:
        success = await uia.pinch(center_x, center_y, zoom_in, scale)
        return {
            "success": success,
            "center": {"x": center_x, "y": center_y},
            "zoom_in": zoom_in,
            "scale": scale,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_drag(
    adb: ADBAdapter,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int,
) -> dict:
    """Drag from one point to another.

    Args:
        adb: ADB adapter
        start_x: Starting X
        start_y: Starting Y
        end_x: Ending X
        end_y: Ending Y
        duration_ms: Drag duration

    Returns:
        Success status
    """
    try:
        # Drag is a slow swipe
        result = await adb.swipe(start_x, start_y, end_x, end_y, duration_ms)
        return {
            "success": result.success,
            "start": {"x": start_x, "y": start_y},
            "end": {"x": end_x, "y": end_y},
            "duration_ms": duration_ms,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_type(
    adb: ADBAdapter,
    uia: UIAutomatorAdapter,
    text: str,
    clear_first: bool,
) -> dict:
    """Type text.

    Args:
        adb: ADB adapter
        uia: UIAutomator adapter
        text: Text to type
        clear_first: Clear field first

    Returns:
        Success status
    """
    try:
        success = await uia.set_text(text, clear_first)
        return {
            "success": success,
            "text": text,
            "cleared_first": clear_first,
        }
    except ADBError as e:
        # Fallback to direct ADB
        try:
            if clear_first:
                await adb.shell("input keyevent 67")  # Delete a few times
                for _ in range(50):
                    await adb.shell("input keyevent 67")

            result = await adb.type_text(text)
            return {
                "success": result.success,
                "text": text,
                "cleared_first": clear_first,
                "error": result.stderr if not result.success else None,
            }
        except ADBError as e2:
            return {"success": False, "error": str(e2)}


async def perform_key_press(adb: ADBAdapter, key: str) -> dict:
    """Press a hardware key.

    Args:
        adb: ADB adapter
        key: Key name

    Returns:
        Success status
    """
    try:
        result = await adb.press_key(key)
        return {
            "success": result.success,
            "key": key,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def perform_tap_elements(
    adb: ADBAdapter,
    uia: UIAutomatorAdapter,
    selectors: list[dict],
    delay_between_ms: int = 200,
) -> dict:
    """Tap multiple elements in sequence.

    Args:
        adb: ADB adapter
        uia: UIAutomator adapter
        selectors: List of selector dicts, each containing text/resource_id/content_desc
        delay_between_ms: Delay between taps in milliseconds

    Returns:
        Results for each tap
    """
    import asyncio

    results = []
    success_count = 0
    fail_count = 0

    for i, selector in enumerate(selectors):
        text = selector.get("text")
        resource_id = selector.get("resource_id")
        content_desc = selector.get("content_desc")

        try:
            # Find element
            elements = await uia.find_elements(
                text=text,
                resource_id=resource_id,
                content_desc=content_desc,
                limit=1,
            )

            if not elements:
                results.append({
                    "index": i,
                    "selector": selector,
                    "success": False,
                    "error": "Element not found",
                })
                fail_count += 1
                continue

            element = elements[0]
            x, y = element.center

            # Perform tap
            result = await adb.tap(x, y)

            if result.success:
                success_count += 1
                results.append({
                    "index": i,
                    "selector": selector,
                    "success": True,
                    "tapped_at": {"x": x, "y": y},
                })
            else:
                fail_count += 1
                results.append({
                    "index": i,
                    "selector": selector,
                    "success": False,
                    "error": result.stderr,
                })

            # Delay before next tap
            if i < len(selectors) - 1 and delay_between_ms > 0:
                await asyncio.sleep(delay_between_ms / 1000.0)

        except Exception as e:
            fail_count += 1
            results.append({
                "index": i,
                "selector": selector,
                "success": False,
                "error": str(e),
            })

    return {
        "total": len(selectors),
        "succeeded": success_count,
        "failed": fail_count,
        "results": results,
    }


async def perform_gesture_path(
    adb: ADBAdapter,
    points: list[dict],
    duration_ms: int = 500,
) -> dict:
    """Perform a gesture following a path of points.

    Args:
        adb: ADB adapter
        points: List of {x, y} coordinate dicts
        duration_ms: Total duration of the gesture

    Returns:
        Success status
    """
    if len(points) < 2:
        return {"success": False, "error": "Need at least 2 points for a gesture"}

    try:
        # Calculate duration per segment
        segments = len(points) - 1
        segment_duration = duration_ms // segments

        # Execute swipes between consecutive points
        for i in range(segments):
            start = points[i]
            end = points[i + 1]
            result = await adb.swipe(
                start["x"], start["y"],
                end["x"], end["y"],
                segment_duration
            )
            if not result.success:
                return {
                    "success": False,
                    "error": f"Gesture failed at segment {i}: {result.stderr}",
                    "completed_segments": i,
                }

        return {
            "success": True,
            "points": len(points),
            "total_duration_ms": duration_ms,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}
