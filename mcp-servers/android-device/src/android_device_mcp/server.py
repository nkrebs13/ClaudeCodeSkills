"""FastMCP server for Android device interaction."""

import asyncio
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ImageContent

from .config import get_config, Config
from .adapters.adb import ADBAdapter
from .adapters.uiautomator import UIAutomatorAdapter
from .persistence.learning_store import LearningStore

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
_adb: Optional[ADBAdapter] = None
_uia: Optional[UIAutomatorAdapter] = None
_learning: Optional[LearningStore] = None


def get_adb() -> ADBAdapter:
    """Get or create ADB adapter."""
    global _adb
    if _adb is None:
        config = get_config()
        _adb = ADBAdapter(device_serial=config.default_device or None)
    return _adb


def get_uia() -> UIAutomatorAdapter:
    """Get or create UIAutomator adapter."""
    global _uia
    if _uia is None:
        _uia = UIAutomatorAdapter(get_adb())
    return _uia


def get_learning() -> LearningStore:
    """Get or create learning store."""
    global _learning
    if _learning is None:
        config = get_config()
        if config.learning_enabled and config.learning_db_path:
            _learning = LearningStore(config.learning_db_path)
        else:
            _learning = LearningStore(None)  # No-op store
    return _learning


# Create the MCP server using FastMCP
server = FastMCP("android-device")


# =============================================================================
# Visual Tools
# =============================================================================


@server.tool()
async def screenshot(
    element_selector: Optional[str] = None,
    format: Optional[str] = None,
    quality: Optional[int] = None,
    save_to_file: Optional[str] = None,
    max_width: Optional[int] = None,
) -> list[ImageContent | TextContent]:
    """Capture a screenshot of the current screen or a specific element.

    Args:
        element_selector: Optional CSS-like selector for a specific element
        format: Image format (png, jpeg, webp). Defaults to config.
        quality: Image quality 1-100. Defaults to config.
        save_to_file: If provided, save screenshot to this file path instead of
                      returning base64 data. Claude Code can then read the file
                      directly using the Read tool. Much more efficient for UI review.
        max_width: Maximum width in pixels. If the screenshot is wider, it will
                   be resized maintaining aspect ratio. Use 800 or 1024 for
                   readable screenshots that don't overwhelm context.

    Returns:
        Screenshot image data, or file path if save_to_file was specified

    Context efficiency tips:
        - Use save_to_file to avoid large base64 data in context
        - Use max_width=800 for readable screenshots at reasonable size
        - Use element_selector to capture just the relevant UI portion
        - Screenshots >500KB are auto-saved to temp file with path returned
    """
    from .tools.visual import take_screenshot

    config = get_config()
    fmt = format or config.screenshot_format
    qual = quality or config.screenshot_quality

    result = await take_screenshot(
        get_adb(),
        get_uia(),
        element_selector=element_selector,
        format=fmt,
        quality=qual,
        save_to_file=save_to_file,
        max_width=max_width,
    )
    return result


@server.tool()
async def get_screen_size() -> dict:
    """Get the device screen resolution.

    Returns:
        Dict with width and height in pixels
    """
    adb = get_adb()
    return await adb.get_screen_size()


@server.tool()
async def get_layout_hierarchy(
    compressed: bool = True,
    max_depth: Optional[int] = None,
    clickable_only: bool = False,
    include_system_ui: bool = True,
) -> str:
    """Get the full UI hierarchy as XML.

    Args:
        compressed: If True, remove verbose attributes to reduce size
        max_depth: Maximum depth of hierarchy to return (None for unlimited).
                   Use 3-5 for most interactive elements.
        clickable_only: If True, only return interactive elements (clickable,
                        focusable, scrollable). Dramatically reduces response size.
        include_system_ui: If True, include system UI (status bar, nav bar).
                           Set to False to focus on app content only.

    Returns:
        XML string of UI hierarchy

    Context efficiency tips:
        - Use clickable_only=True for ~80% size reduction
        - Use max_depth=5 to exclude deep nested layouts
        - Use include_system_ui=False to exclude system chrome
        - Prefer get_layout_bounds() for even lighter responses
    """
    from .tools.visual import get_hierarchy

    return await get_hierarchy(
        get_uia(),
        compressed=compressed,
        max_depth=max_depth,
        clickable_only=clickable_only,
        include_system_ui=include_system_ui,
    )


@server.tool()
async def get_layout_bounds(
    clickable_only: bool = False,
    include_system_ui: bool = True,
    limit: int = 100,
) -> list[dict]:
    """Get bounding boxes for all visible elements (faster than full hierarchy).

    This is the most context-efficient way to understand screen layout.
    Returns ~10x fewer tokens than get_layout_hierarchy.

    Args:
        clickable_only: If True, only return interactive elements
        include_system_ui: If True, include system UI elements
        limit: Maximum number of elements to return (default 100)

    Returns:
        List of element bounds with basic info (text, resource_id, bounds, clickable)

    Context efficiency tips:
        - Use clickable_only=True to focus on tappable elements
        - Use limit=20 for quick overview of main interactive elements
        - Use this tool BEFORE get_layout_hierarchy to assess complexity
    """
    from .tools.visual import get_bounds

    return await get_bounds(
        get_uia(),
        clickable_only=clickable_only,
        include_system_ui=include_system_ui,
        limit=limit,
    )


@server.tool()
async def find_element(
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    class_name: Optional[str] = None,
    content_desc: Optional[str] = None,
    xpath: Optional[str] = None,
) -> Optional[dict]:
    """Find a single UI element by selector.

    Args:
        text: Match by visible text
        resource_id: Match by resource ID (e.g., 'com.app:id/button')
        class_name: Match by class (e.g., 'android.widget.Button')
        content_desc: Match by content description (accessibility)
        xpath: XPath selector

    Returns:
        Element info dict or None if not found
    """
    from .tools.visual import find_single_element

    return await find_single_element(
        get_uia(),
        get_learning(),
        text=text,
        resource_id=resource_id,
        class_name=class_name,
        content_desc=content_desc,
        xpath=xpath,
    )


@server.tool()
async def find_elements(
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    class_name: Optional[str] = None,
    content_desc: Optional[str] = None,
    xpath: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Find all matching UI elements.

    Args:
        text: Match by visible text
        resource_id: Match by resource ID
        class_name: Match by class
        content_desc: Match by content description
        xpath: XPath selector
        limit: Maximum number of elements to return

    Returns:
        List of element info dicts
    """
    from .tools.visual import find_multiple_elements

    return await find_multiple_elements(
        get_uia(),
        text=text,
        resource_id=resource_id,
        class_name=class_name,
        content_desc=content_desc,
        xpath=xpath,
        limit=limit,
    )


@server.tool()
async def screen_record_start(max_duration: int = 180) -> dict:
    """Start recording the screen.

    Args:
        max_duration: Maximum recording duration in seconds (default 180)

    Returns:
        Recording session info
    """
    from .tools.visual import start_recording

    return await start_recording(get_adb(), max_duration=max_duration)


@server.tool()
async def screen_record_stop() -> list[ImageContent | TextContent]:
    """Stop screen recording and return the video.

    Returns:
        Video file data
    """
    from .tools.visual import stop_recording

    return await stop_recording(get_adb())


# =============================================================================
# Interaction Tools
# =============================================================================


@server.tool()
async def tap(x: int, y: int) -> dict:
    """Tap at specific coordinates.

    Args:
        x: X coordinate in pixels
        y: Y coordinate in pixels

    Returns:
        Success status
    """
    from .tools.interaction import perform_tap

    return await perform_tap(get_adb(), x, y)


@server.tool()
async def tap_element(
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    content_desc: Optional[str] = None,
    xpath: Optional[str] = None,
    index: int = 0,
) -> dict:
    """Tap on a UI element by selector.

    Args:
        text: Match by visible text
        resource_id: Match by resource ID
        content_desc: Match by content description
        xpath: XPath selector
        index: If multiple matches, tap this index (0-based)

    Returns:
        Success status with element info
    """
    from .tools.interaction import perform_tap_element

    return await perform_tap_element(
        get_adb(),
        get_uia(),
        get_learning(),
        text=text,
        resource_id=resource_id,
        content_desc=content_desc,
        xpath=xpath,
        index=index,
    )


@server.tool()
async def double_tap(x: int, y: int) -> dict:
    """Double tap at coordinates.

    Args:
        x: X coordinate
        y: Y coordinate

    Returns:
        Success status
    """
    from .tools.interaction import perform_double_tap

    return await perform_double_tap(get_adb(), x, y)


@server.tool()
async def long_press(x: int, y: int, duration_ms: int = 1000) -> dict:
    """Long press at coordinates.

    Args:
        x: X coordinate
        y: Y coordinate
        duration_ms: Press duration in milliseconds

    Returns:
        Success status
    """
    from .tools.interaction import perform_long_press

    return await perform_long_press(get_adb(), x, y, duration_ms)


@server.tool()
async def swipe(
    start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 300
) -> dict:
    """Swipe from one point to another.

    Args:
        start_x: Starting X coordinate
        start_y: Starting Y coordinate
        end_x: Ending X coordinate
        end_y: Ending Y coordinate
        duration_ms: Swipe duration in milliseconds

    Returns:
        Success status
    """
    from .tools.interaction import perform_swipe

    return await perform_swipe(get_adb(), start_x, start_y, end_x, end_y, duration_ms)


@server.tool()
async def scroll(direction: str, amount: float = 0.5) -> dict:
    """Scroll the screen in a direction.

    Args:
        direction: 'up', 'down', 'left', or 'right'
        amount: Scroll amount as fraction of screen (0.0-1.0)

    Returns:
        Success status
    """
    from .tools.interaction import perform_scroll

    return await perform_scroll(get_adb(), direction, amount)


@server.tool()
async def pinch(center_x: int, center_y: int, zoom_in: bool = True, scale: float = 0.5) -> dict:
    """Pinch zoom gesture.

    Args:
        center_x: Center X coordinate
        center_y: Center Y coordinate
        zoom_in: True to zoom in, False to zoom out
        scale: Scale factor (0.0-1.0)

    Returns:
        Success status
    """
    from .tools.interaction import perform_pinch

    return await perform_pinch(get_uia(), center_x, center_y, zoom_in, scale)


@server.tool()
async def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 500) -> dict:
    """Drag from one point to another (long press then move).

    Args:
        start_x: Starting X
        start_y: Starting Y
        end_x: Ending X
        end_y: Ending Y
        duration_ms: Drag duration

    Returns:
        Success status
    """
    from .tools.interaction import perform_drag

    return await perform_drag(get_adb(), start_x, start_y, end_x, end_y, duration_ms)


@server.tool()
async def type_text(text: str, clear_first: bool = False) -> dict:
    """Type text using the keyboard.

    Args:
        text: Text to type
        clear_first: If True, clear the field first

    Returns:
        Success status
    """
    from .tools.interaction import perform_type

    return await perform_type(get_adb(), get_uia(), text, clear_first)


@server.tool()
async def press_key(key: str) -> dict:
    """Press a hardware or navigation key.

    Args:
        key: Key name (back, home, menu, enter, delete, volume_up, volume_down, power, etc.)

    Returns:
        Success status
    """
    from .tools.interaction import perform_key_press

    return await perform_key_press(get_adb(), key)


@server.tool()
async def tap_elements(
    selectors: list[dict],
    delay_between_ms: int = 200,
) -> dict:
    """Tap multiple elements in sequence (batch operation).

    Args:
        selectors: List of selector dicts, each containing text/resource_id/content_desc
        delay_between_ms: Delay between taps in milliseconds

    Returns:
        Results for each tap with success counts

    Example:
        tap_elements([
            {"text": "Accept"},
            {"resource_id": "com.app:id/next_button"},
            {"content_desc": "Continue"}
        ])
    """
    from .tools.interaction import perform_tap_elements

    return await perform_tap_elements(
        get_adb(),
        get_uia(),
        selectors=selectors,
        delay_between_ms=delay_between_ms,
    )


@server.tool()
async def gesture_path(
    points: list[dict],
    duration_ms: int = 500,
) -> dict:
    """Perform a gesture following a path of points.

    Useful for drawing gestures, unlocking patterns, or complex swipes.

    Args:
        points: List of {x, y} coordinate dicts (minimum 2 points)
        duration_ms: Total duration of the gesture in milliseconds

    Returns:
        Success status

    Example:
        gesture_path([
            {"x": 100, "y": 100},
            {"x": 200, "y": 200},
            {"x": 300, "y": 100}
        ], duration_ms=1000)
    """
    from .tools.interaction import perform_gesture_path

    return await perform_gesture_path(
        get_adb(),
        points=points,
        duration_ms=duration_ms,
    )


# =============================================================================
# Observation Tools
# =============================================================================


@server.tool()
async def device_info() -> dict:
    """Get device information.

    Returns:
        Dict with model, API level, Android version, screen size, etc.
    """
    from .tools.observation import get_device_info

    return await get_device_info(get_adb())


@server.tool()
async def shell(command: str) -> dict:
    """Execute a shell command on the device.

    Args:
        command: Shell command to execute

    Returns:
        Command output and exit code
    """
    from .tools.observation import execute_shell

    config = get_config()
    return await execute_shell(
        get_adb(),
        command,
        allowed=config.allow_shell_commands,
        allowlist=config.shell_command_allowlist,
    )


@server.tool()
async def logcat(
    lines: Optional[int] = None,
    filter_tag: Optional[str] = None,
    filter_level: Optional[str] = None,
    filter_package: Optional[str] = None,
    since: Optional[str] = None,
) -> str:
    """Get recent logcat output.

    Args:
        lines: Number of lines to return (default from config)
        filter_tag: Filter by log tag
        filter_level: Minimum log level (V, D, I, W, E, F)
        filter_package: Filter by package name
        since: Get logs since timestamp (format: 'MM-DD HH:MM:SS.mmm')

    Returns:
        Log output as string
    """
    from .tools.observation import get_logcat

    config = get_config()
    return await get_logcat(
        get_adb(),
        lines=lines or config.logcat_default_lines,
        tag=filter_tag,
        level=filter_level,
        package=filter_package,
        since=since,
    )


@server.tool()
async def get_current_activity() -> dict:
    """Get the current foreground activity.

    Returns:
        Activity name and package
    """
    from .tools.observation import get_foreground_activity

    return await get_foreground_activity(get_adb())


@server.tool()
async def get_current_package() -> str:
    """Get the current foreground package name.

    Returns:
        Package name string
    """
    from .tools.observation import get_foreground_package

    return await get_foreground_package(get_adb())


@server.tool()
async def wait_for_element(
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    timeout_ms: int = 10000,
    poll_interval_ms: int = 500,
) -> dict:
    """Wait for an element to appear on screen.

    Args:
        text: Match by visible text
        resource_id: Match by resource ID
        timeout_ms: Maximum wait time in milliseconds
        poll_interval_ms: Polling interval

    Returns:
        Element info if found, or timeout error
    """
    from .tools.observation import wait_for_element_visible

    return await wait_for_element_visible(
        get_uia(),
        text=text,
        resource_id=resource_id,
        timeout_ms=timeout_ms,
        poll_interval_ms=poll_interval_ms,
    )


@server.tool()
async def wait_for_idle(timeout_ms: int = 5000) -> dict:
    """Wait for UI to become idle (animations complete).

    Args:
        timeout_ms: Maximum wait time

    Returns:
        Success status
    """
    from .tools.observation import wait_for_ui_idle

    return await wait_for_ui_idle(get_uia(), timeout_ms)


@server.tool()
async def wait_for_text(
    text: str,
    timeout_ms: int = 10000,
    poll_interval_ms: int = 500,
    partial: bool = False,
) -> dict:
    """Wait for specific text to appear on screen.

    Args:
        text: Text to wait for
        timeout_ms: Maximum wait time in milliseconds
        poll_interval_ms: Polling interval
        partial: If True, matches partial text (contains)

    Returns:
        Element info if found, or timeout error
    """
    from .tools.observation import wait_for_text as _wait_for_text

    return await _wait_for_text(
        get_uia(),
        text=text,
        timeout_ms=timeout_ms,
        poll_interval_ms=poll_interval_ms,
        partial=partial,
    )


@server.tool()
async def get_focused_element() -> dict:
    """Get the currently focused UI element.

    Returns:
        Element info or error if no element is focused
    """
    from .tools.observation import get_focused_element as _get_focused

    return await _get_focused(get_uia())


@server.tool()
async def get_toast_messages(timeout_ms: int = 3000) -> dict:
    """Attempt to capture recent toast messages.

    Note: Toast messages are transient and difficult to capture reliably.
    This uses logcat to find toast-related log entries.

    Args:
        timeout_ms: How far back to look for toasts

    Returns:
        List of recent toast messages or empty if none found
    """
    from .tools.observation import get_toast_messages as _get_toasts

    return await _get_toasts(get_adb(), timeout_ms=timeout_ms)


# =============================================================================
# App Management Tools
# =============================================================================


@server.tool()
async def install_apk(apk_path: str, replace: bool = True) -> dict:
    """Install an APK file.

    Args:
        apk_path: Path to APK file on host machine
        replace: If True, replace existing app

    Returns:
        Installation result
    """
    from .tools.app_management import install_application

    return await install_application(get_adb(), apk_path, replace)


@server.tool()
async def uninstall_app(package: str, keep_data: bool = False) -> dict:
    """Uninstall an app.

    Args:
        package: Package name (e.g., 'com.example.app')
        keep_data: If True, keep app data

    Returns:
        Uninstall result
    """
    from .tools.app_management import uninstall_application

    return await uninstall_application(get_adb(), package, keep_data)


@server.tool()
async def launch_app(package: str, activity: Optional[str] = None, wait: bool = True) -> dict:
    """Launch an app.

    Args:
        package: Package name
        activity: Specific activity to launch (optional)
        wait: Wait for app to start

    Returns:
        Launch result
    """
    from .tools.app_management import launch_application

    return await launch_application(get_adb(), package, activity, wait)


@server.tool()
async def stop_app(package: str) -> dict:
    """Force stop an app.

    Args:
        package: Package name

    Returns:
        Stop result
    """
    from .tools.app_management import stop_application

    return await stop_application(get_adb(), package)


@server.tool()
async def clear_app_data(package: str) -> dict:
    """Clear app data and cache.

    Args:
        package: Package name

    Returns:
        Clear result
    """
    from .tools.app_management import clear_application_data

    return await clear_application_data(get_adb(), package)


@server.tool()
async def list_packages(
    filter_type: Optional[str] = None, filter_text: Optional[str] = None
) -> list[str]:
    """List installed packages.

    Args:
        filter_type: 'system', 'third-party', or None for all
        filter_text: Filter by package name substring

    Returns:
        List of package names
    """
    from .tools.app_management import list_installed_packages

    return await list_installed_packages(get_adb(), filter_type, filter_text)


@server.tool()
async def get_app_info(package: str) -> dict:
    """Get detailed app information.

    Args:
        package: Package name

    Returns:
        App version, permissions, activities, etc.
    """
    from .tools.app_management import get_application_info

    return await get_application_info(get_adb(), package)


# =============================================================================
# Learning Tools
# =============================================================================


@server.tool()
async def pattern_save(
    app_package: str,
    pattern_key: str,
    pattern_type: str,
    pattern_data: dict,
    app_version: Optional[str] = None,
) -> dict:
    """Save a learned pattern for future use.

    Args:
        app_package: App package name
        pattern_key: Unique key for this pattern (e.g., 'LoginButton')
        pattern_type: Type: 'element', 'flow', 'strategy', or 'failure'
        pattern_data: Pattern data as dict
        app_version: Optional app version

    Returns:
        Save confirmation
    """
    from .tools.learning import save_pattern

    return await save_pattern(
        get_learning(), app_package, pattern_key, pattern_type, pattern_data, app_version
    )


@server.tool()
async def pattern_get(app_package: str, pattern_key: str) -> Optional[dict]:
    """Retrieve a saved pattern.

    Args:
        app_package: App package name
        pattern_key: Pattern key

    Returns:
        Pattern data or None if not found
    """
    from .tools.learning import get_pattern

    return await get_pattern(get_learning(), app_package, pattern_key)


@server.tool()
async def pattern_list(
    app_package: str, pattern_type: Optional[str] = None, limit: int = 100
) -> list[dict]:
    """List patterns for an app.

    Args:
        app_package: App package name
        pattern_type: Optional filter by type
        limit: Maximum patterns to return

    Returns:
        List of pattern summaries
    """
    from .tools.learning import list_patterns

    return await list_patterns(get_learning(), app_package, pattern_type, limit)


@server.tool()
async def pattern_delete(app_package: str, pattern_key: str) -> dict:
    """Delete a pattern.

    Args:
        app_package: App package name
        pattern_key: Pattern key

    Returns:
        Deletion result
    """
    from .tools.learning import delete_pattern

    return await delete_pattern(get_learning(), app_package, pattern_key)


@server.tool()
async def interaction_log(
    app_package: str,
    action_type: str,
    target_selector: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> dict:
    """Log an interaction for reliability tracking.

    Args:
        app_package: App package name
        action_type: Type of action (tap, swipe, etc.)
        target_selector: Selector used
        success: Whether action succeeded
        error_message: Error message if failed
        latency_ms: Action latency

    Returns:
        Log confirmation
    """
    from .tools.learning import log_interaction

    return await log_interaction(
        get_learning(), app_package, action_type, target_selector, success, error_message, latency_ms
    )


@server.tool()
async def get_reliability_stats(app_package: str, days: int = 30) -> dict:
    """Get reliability statistics for an app.

    Args:
        app_package: App package name
        days: Number of days to analyze

    Returns:
        Success rates by action type
    """
    from .tools.learning import get_stats

    return await get_stats(get_learning(), app_package, days)


# =============================================================================
# Server Entry Point
# =============================================================================


def main() -> None:
    """Main entry point."""
    logger.info("Starting Android Device MCP Server...")
    server.run()


if __name__ == "__main__":
    main()
