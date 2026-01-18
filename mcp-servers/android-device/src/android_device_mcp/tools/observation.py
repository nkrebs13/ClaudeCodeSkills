"""Observation tools for device info, logs, and shell commands."""

import logging
import re
from typing import Optional

from ..adapters.adb import ADBAdapter, ADBError
from ..adapters.uiautomator import UIAutomatorAdapter

logger = logging.getLogger(__name__)

# Dangerous commands that should never be allowed
BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    "> /dev/",
    "chmod 777 /",
    ":(){ :|:& };:",  # Fork bomb
}


def _is_command_safe(command: str, allowlist: list[str]) -> tuple[bool, str]:
    """Check if a shell command is safe to execute.

    Args:
        command: The command to check
        allowlist: If non-empty, only allow these commands

    Returns:
        Tuple of (is_safe, reason)
    """
    # Check blocked patterns
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return False, f"Blocked pattern detected: {blocked}"

    # If allowlist is set, check against it
    if allowlist:
        cmd_base = command.split()[0] if command.split() else ""
        if cmd_base not in allowlist:
            return False, f"Command '{cmd_base}' not in allowlist"

    return True, ""


async def get_device_info(adb: ADBAdapter) -> dict:
    """Get comprehensive device information.

    Args:
        adb: ADB adapter

    Returns:
        Device info dict
    """
    try:
        info = await adb.get_device_info()
        info["connected"] = True
        return info
    except ADBError as e:
        return {"connected": False, "error": str(e)}


async def execute_shell(
    adb: ADBAdapter,
    command: str,
    allowed: bool = True,
    allowlist: Optional[list[str]] = None,
) -> dict:
    """Execute a shell command on the device.

    Args:
        adb: ADB adapter
        command: Shell command
        allowed: Whether shell commands are allowed
        allowlist: Optional command allowlist

    Returns:
        Command output and status
    """
    if not allowed:
        return {
            "success": False,
            "error": "Shell commands are disabled in configuration",
        }

    # Security check
    is_safe, reason = _is_command_safe(command, allowlist or [])
    if not is_safe:
        return {
            "success": False,
            "error": f"Command blocked: {reason}",
        }

    try:
        result = await adb.shell(command)
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def get_logcat(
    adb: ADBAdapter,
    lines: int = 100,
    tag: Optional[str] = None,
    level: Optional[str] = None,
    package: Optional[str] = None,
    since: Optional[str] = None,
) -> str:
    """Get logcat output.

    Args:
        adb: ADB adapter
        lines: Number of lines
        tag: Filter by tag
        level: Minimum level
        package: Filter by package name (filters by process ID)
        since: Logs since timestamp

    Returns:
        Log output
    """
    try:
        # If package filter requested, try multiple methods
        pids: list[str] = []
        if package:
            # Method 1: Get PIDs using pidof (handles multiple processes)
            result = await adb.shell(f"pidof {package}")
            if result.success and result.stdout.strip():
                pids = result.stdout.strip().split()

            # Method 2: If app not running, try ps to find any related processes
            if not pids:
                result = await adb.shell(f"ps -A | grep {package}")
                if result.success and result.stdout.strip():
                    # ps output: USER PID PPID VSZ RSS WCHAN ADDR S NAME
                    for line in result.stdout.strip().split("\n"):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            pids.append(parts[1])

        # Get logcat output
        output = await adb.get_logcat(
            lines=lines * 2 if pids else lines,  # Get more if filtering
            tag=tag,
            level=level,
            since=since,
        )

        # Filter by PIDs if needed using proper log format matching
        if pids:
            filtered_lines = []
            # Logcat format: "MM-DD HH:MM:SS.mmm PID TID LEVEL TAG: message"
            # or "DATE TIME PID TID LEVEL TAG: message"
            pid_pattern = re.compile(
                r"^\s*\S+\s+\S+\s+(" + "|".join(re.escape(p) for p in pids) + r")\s+"
            )
            for line in output.split("\n"):
                if pid_pattern.match(line):
                    filtered_lines.append(line)
            output = "\n".join(filtered_lines[-lines:])

            if not output.strip():
                return f"No logs found for package '{package}' (PIDs: {', '.join(pids)}). The app may not have generated any logs recently."

        return output

    except ADBError as e:
        return f"Error getting logcat: {e}"


async def get_foreground_activity(adb: ADBAdapter) -> dict:
    """Get the current foreground activity.

    Args:
        adb: ADB adapter

    Returns:
        Activity info
    """
    try:
        return await adb.get_current_activity()
    except ADBError as e:
        return {"error": str(e)}


async def get_foreground_package(adb: ADBAdapter) -> str:
    """Get the current foreground package.

    Args:
        adb: ADB adapter

    Returns:
        Package name
    """
    try:
        return await adb.get_current_package()
    except ADBError:
        return "unknown"


async def wait_for_element_visible(
    uia: UIAutomatorAdapter,
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    timeout_ms: int = 10000,
    poll_interval_ms: int = 500,
) -> dict:
    """Wait for an element to appear.

    Args:
        uia: UIAutomator adapter
        text: Match by text
        resource_id: Match by resource ID
        timeout_ms: Timeout in ms
        poll_interval_ms: Poll interval

    Returns:
        Element info or timeout error
    """
    try:
        element = await uia.wait_for_element(
            text=text,
            resource_id=resource_id,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
        )

        if element:
            return {
                "found": True,
                "element": element.to_dict(),
            }
        else:
            selector = text or resource_id
            return {
                "found": False,
                "error": f"Element not found within {timeout_ms}ms: {selector}",
            }

    except Exception as e:
        return {"found": False, "error": str(e)}


async def wait_for_ui_idle(uia: UIAutomatorAdapter, timeout_ms: int) -> dict:
    """Wait for UI to become idle.

    Args:
        uia: UIAutomator adapter
        timeout_ms: Timeout

    Returns:
        Success status
    """
    try:
        success = await uia.wait_for_idle(timeout_ms)
        return {"success": success, "timeout_ms": timeout_ms}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def wait_for_text(
    uia: UIAutomatorAdapter,
    text: str,
    timeout_ms: int = 10000,
    poll_interval_ms: int = 500,
    partial: bool = False,
) -> dict:
    """Wait for specific text to appear on screen.

    Args:
        uia: UIAutomator adapter
        text: Text to wait for
        timeout_ms: Maximum wait time in milliseconds
        poll_interval_ms: Polling interval
        partial: If True, matches partial text (contains)

    Returns:
        Element info if found, or timeout error
    """
    import asyncio
    import time

    start_time = time.time()
    timeout_sec = timeout_ms / 1000.0
    poll_sec = poll_interval_ms / 1000.0

    while (time.time() - start_time) < timeout_sec:
        try:
            if partial:
                # Find elements containing the text
                elements = await uia.find_elements(text=text, limit=1)
                if not elements:
                    # Try via XPath for partial match
                    elements = await uia.find_elements(
                        xpath=f"//*[contains(@text, '{text}')]",
                        limit=1
                    )
            else:
                elements = await uia.find_elements(text=text, limit=1)

            if elements:
                return {
                    "found": True,
                    "text": text,
                    "element": elements[0].to_dict(),
                    "elapsed_ms": int((time.time() - start_time) * 1000),
                }
        except Exception as e:
            logger.debug(f"Error during text search: {e}")

        await asyncio.sleep(poll_sec)

    return {
        "found": False,
        "text": text,
        "error": f"Text '{text}' not found within {timeout_ms}ms",
        "elapsed_ms": timeout_ms,
    }


async def get_focused_element(uia: UIAutomatorAdapter) -> dict:
    """Get the currently focused UI element.

    Args:
        uia: UIAutomator adapter

    Returns:
        Element info or error
    """
    try:
        # Find element with focused=true attribute
        elements = await uia.find_elements(xpath="//*[@focused='true']", limit=1)

        if elements:
            return {
                "found": True,
                "element": elements[0].to_dict(),
            }

        return {
            "found": False,
            "error": "No focused element found",
        }
    except Exception as e:
        return {"found": False, "error": str(e)}


async def get_toast_messages(
    adb: ADBAdapter,
    timeout_ms: int = 3000,
) -> dict:
    """Attempt to capture recent toast messages.

    Note: Toast messages are transient and difficult to capture reliably.
    This uses logcat to find toast-related log entries.

    Args:
        adb: ADB adapter
        timeout_ms: How far back to look for toasts (not fully used yet)

    Returns:
        List of recent toast messages or empty if none found
    """
    try:
        # Look for toast-related log entries
        # Different manufacturers log toasts differently
        result = await adb.shell(
            "logcat -d -t 100 | grep -iE 'Toast|makeText|showToast' | tail -10"
        )

        messages = []
        if result.success and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                # Extract message from log line
                if ":" in line:
                    msg_part = line.split(":", 1)[-1].strip()
                    if msg_part:
                        messages.append(msg_part)

        return {
            "found": len(messages) > 0,
            "count": len(messages),
            "messages": messages,
            "note": "Toast capture is best-effort; some toasts may be missed",
        }
    except Exception as e:
        return {"found": False, "error": str(e)}
