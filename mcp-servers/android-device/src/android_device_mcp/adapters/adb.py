"""ADB (Android Debug Bridge) adapter for device communication."""

import asyncio
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ADBError(Exception):
    """Error from ADB command execution."""

    def __init__(self, message: str, exit_code: int = 1, stderr: str = ""):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


@dataclass
class CommandResult:
    """Result from an ADB command."""

    stdout: str
    stderr: str
    exit_code: int

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class ADBAdapter:
    """Adapter for ADB command execution.

    Security: Uses asyncio.create_subprocess_exec which does NOT use shell
    parsing, preventing command injection attacks.
    """

    # Key code mapping for press_key
    KEY_CODES = {
        "back": 4,
        "home": 3,
        "menu": 82,
        "enter": 66,
        "delete": 67,
        "backspace": 67,
        "tab": 61,
        "space": 62,
        "volume_up": 24,
        "volume_down": 25,
        "power": 26,
        "camera": 27,
        "search": 84,
        "dpad_up": 19,
        "dpad_down": 20,
        "dpad_left": 21,
        "dpad_right": 22,
        "dpad_center": 23,
        "app_switch": 187,
        "recent": 187,
    }

    def __init__(self, device_serial: Optional[str] = None, adb_path: Optional[str] = None):
        """Initialize ADB adapter.

        Args:
            device_serial: Specific device serial to target (None = first device)
            adb_path: Path to adb binary (None = find in PATH)
        """
        self.device_serial = device_serial
        self.adb_path = adb_path or self._find_adb()
        self._screen_size: Optional[tuple[int, int]] = None
        self._recording_process: Optional[asyncio.subprocess.Process] = None
        self._recording_path: Optional[str] = None

    def _find_adb(self) -> str:
        """Find ADB binary in PATH or common locations."""
        # Check PATH
        adb = shutil.which("adb")
        if adb:
            return adb

        # Check common locations
        common_paths = [
            os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
            os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
            "/usr/local/bin/adb",
            "/opt/android-sdk/platform-tools/adb",
        ]

        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        # Check ANDROID_HOME
        android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if android_home:
            adb = os.path.join(android_home, "platform-tools", "adb")
            if os.path.isfile(adb):
                return adb

        raise ADBError("ADB not found. Please install Android SDK platform-tools and add to PATH.")

    def _build_command(self, *args: str) -> list[str]:
        """Build ADB command with device serial if specified."""
        cmd = [self.adb_path]
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])
        cmd.extend(args)
        return cmd

    async def run(self, *args: str, timeout: float = 30.0) -> CommandResult:
        """Run an ADB command.

        Security: Uses create_subprocess_exec (not shell=True) to prevent injection.

        Args:
            *args: Command arguments (e.g., 'shell', 'ls')
            timeout: Command timeout in seconds

        Returns:
            CommandResult with stdout, stderr, exit_code
        """
        cmd = self._build_command(*args)
        logger.debug(f"Running ADB command: {' '.join(cmd)}")

        try:
            # Using create_subprocess_exec - safe, no shell parsing
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return CommandResult(
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            raise ADBError(f"ADB command timed out after {timeout}s: {' '.join(args)}")
        except Exception as e:
            raise ADBError(f"ADB command failed: {e}")

    async def run_binary(self, *args: str, timeout: float = 30.0) -> bytes:
        """Run an ADB command that returns binary data (e.g., screenshots).

        Security: Uses create_subprocess_exec (not shell=True) to prevent injection.

        Args:
            *args: Command arguments (e.g., 'exec-out', 'screencap', '-p')
            timeout: Command timeout in seconds

        Returns:
            Raw binary stdout data

        Raises:
            ADBError: If command fails or times out
        """
        cmd = self._build_command(*args)
        logger.debug(f"Running ADB binary command: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode != 0:
                raise ADBError(
                    f"Command failed: {stderr.decode('utf-8', errors='replace')}",
                    exit_code=proc.returncode or 1,
                    stderr=stderr.decode("utf-8", errors="replace"),
                )

            return stdout
        except asyncio.TimeoutError:
            raise ADBError(f"ADB command timed out after {timeout}s: {' '.join(args)}")
        except ADBError:
            raise
        except Exception as e:
            raise ADBError(f"ADB command failed: {e}")

    async def shell(self, command: str, timeout: float = 30.0) -> CommandResult:
        """Run a shell command on the device.

        Note: The command is passed as a single argument to 'adb shell',
        which executes it on the device. This is intentional device-side
        shell execution, not host-side shell parsing.

        Args:
            command: Shell command to execute
            timeout: Command timeout

        Returns:
            CommandResult
        """
        return await self.run("shell", command, timeout=timeout)

    async def check_connection(self) -> bool:
        """Check if device is connected and accessible."""
        result = await self.run("devices")
        if not result.success:
            return False

        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:  # Skip header
            parts = line.strip().split()
            if len(parts) >= 2:
                serial, state = parts[0], parts[1]
                if state == "device":
                    if self.device_serial is None or serial == self.device_serial:
                        if self.device_serial is None:
                            self.device_serial = serial
                        return True
        return False

    async def get_device_serial(self) -> str:
        """Get the device serial, connecting if needed."""
        if self.device_serial:
            return self.device_serial

        result = await self.run("devices")
        if not result.success:
            raise ADBError("Failed to list devices")

        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                self.device_serial = parts[0]
                return self.device_serial

        raise ADBError("No connected devices found")

    async def get_screen_size(self) -> dict:
        """Get device screen size.

        Returns:
            Dict with 'width' and 'height'
        """
        if self._screen_size:
            return {"width": self._screen_size[0], "height": self._screen_size[1]}

        result = await self.shell("wm size")
        if not result.success:
            raise ADBError("Failed to get screen size")

        # Parse "Physical size: 1080x2340"
        match = re.search(r"(\d+)x(\d+)", result.stdout)
        if not match:
            raise ADBError(f"Could not parse screen size: {result.stdout}")

        width, height = int(match.group(1)), int(match.group(2))
        self._screen_size = (width, height)
        return {"width": width, "height": height}

    async def get_device_info(self) -> dict:
        """Get comprehensive device information."""
        # Run multiple commands in parallel
        tasks = [
            self.shell("getprop ro.product.model"),
            self.shell("getprop ro.product.manufacturer"),
            self.shell("getprop ro.build.version.release"),
            self.shell("getprop ro.build.version.sdk"),
            self.shell("getprop ro.product.device"),
            self.shell("getprop ro.serialno"),
            self.get_screen_size(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        def get_value(result: CommandResult | dict | Exception) -> str:
            if isinstance(result, Exception):
                return "unknown"
            if isinstance(result, dict):
                return str(result)
            return result.stdout.strip()

        screen_size = results[6] if isinstance(results[6], dict) else {"width": 0, "height": 0}

        return {
            "model": get_value(results[0]),
            "manufacturer": get_value(results[1]),
            "android_version": get_value(results[2]),
            "api_level": int(get_value(results[3])) if get_value(results[3]).isdigit() else 0,
            "device": get_value(results[4]),
            "serial": get_value(results[5]),
            "screen_width": screen_size.get("width", 0),
            "screen_height": screen_size.get("height", 0),
        }

    async def screenshot(self, local_path: Optional[str] = None) -> bytes:
        """Capture a screenshot.

        Args:
            local_path: Optional path to save the file

        Returns:
            PNG image bytes
        """
        try:
            # Use run_binary for proper binary data handling
            png_data = await self.run_binary("exec-out", "screencap", "-p", timeout=10.0)

            # Validate it's actually PNG data
            if not png_data.startswith(b"\x89PNG"):
                raise ADBError("Invalid screenshot data: not a valid PNG")

            if local_path:
                Path(local_path).write_bytes(png_data)

            return png_data
        except ADBError:
            # Fallback to file-based method if exec-out fails
            logger.warning("exec-out screenshot failed, falling back to file method")
            return await self.screenshot_to_file()

    async def screenshot_to_file(self) -> bytes:
        """Capture screenshot via file (fallback method).

        This is slower but more reliable on some devices.
        """
        remote_path = "/sdcard/screenshot_tmp.png"

        # Capture to file
        result = await self.shell(f"screencap -p {remote_path}")
        if not result.success:
            raise ADBError(f"Screenshot capture failed: {result.stderr}")

        try:
            # Pull the file
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                local_path = tmp.name

            pull_result = await self.run("pull", remote_path, local_path, timeout=10.0)
            if not pull_result.success:
                raise ADBError(f"Screenshot pull failed: {pull_result.stderr}")

            return Path(local_path).read_bytes()
        finally:
            # Clean up
            await self.shell(f"rm {remote_path}")
            if os.path.exists(local_path):
                os.unlink(local_path)

    async def tap(self, x: int, y: int) -> CommandResult:
        """Tap at coordinates."""
        return await self.shell(f"input tap {x} {y}")

    async def double_tap(self, x: int, y: int) -> CommandResult:
        """Double tap at coordinates."""
        return await self.shell(f"input tap {x} {y} && input tap {x} {y}")

    async def long_press(self, x: int, y: int, duration_ms: int = 1000) -> CommandResult:
        """Long press at coordinates."""
        return await self.shell(f"input swipe {x} {y} {x} {y} {duration_ms}")

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> CommandResult:
        """Swipe from (x1,y1) to (x2,y2)."""
        return await self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    async def type_text(self, text: str) -> CommandResult:
        """Type text (escapes special characters)."""
        # Escape special shell characters
        escaped = text.replace("\\", "\\\\")
        escaped = escaped.replace('"', '\\"')
        escaped = escaped.replace("'", "\\'")
        escaped = escaped.replace(" ", "%s")
        escaped = escaped.replace("&", "\\&")
        escaped = escaped.replace("<", "\\<")
        escaped = escaped.replace(">", "\\>")
        escaped = escaped.replace("|", "\\|")
        escaped = escaped.replace(";", "\\;")
        escaped = escaped.replace("(", "\\(")
        escaped = escaped.replace(")", "\\)")

        return await self.shell(f"input text '{escaped}'")

    async def press_key(self, key: str | int) -> CommandResult:
        """Press a key by name or keycode."""
        if isinstance(key, str):
            key_lower = key.lower().replace(" ", "_")
            if key_lower in self.KEY_CODES:
                keycode = self.KEY_CODES[key_lower]
            else:
                raise ADBError(f"Unknown key: {key}. Valid keys: {list(self.KEY_CODES.keys())}")
        else:
            keycode = key

        return await self.shell(f"input keyevent {keycode}")

    async def start_screen_record(
        self, remote_path: str = "/sdcard/screenrecord.mp4", max_duration: int = 180
    ) -> None:
        """Start screen recording (runs in background)."""
        if self._recording_process:
            raise ADBError("Recording already in progress")

        cmd = self._build_command(
            "shell", f"screenrecord --time-limit {max_duration} {remote_path}"
        )

        self._recording_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._recording_path = remote_path

    async def stop_screen_record(self) -> bytes:
        """Stop screen recording and return the video file."""
        if not self._recording_process:
            raise ADBError("No recording in progress")

        # Send interrupt to stop recording
        self._recording_process.terminate()
        try:
            await asyncio.wait_for(self._recording_process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            self._recording_process.kill()

        await asyncio.sleep(0.5)  # Wait for file to be written

        # Pull the recording
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            local_path = tmp.name

        try:
            result = await self.run("pull", self._recording_path, local_path, timeout=60.0)
            if not result.success:
                raise ADBError(f"Failed to pull recording: {result.stderr}")

            data = Path(local_path).read_bytes()
        finally:
            # Clean up
            await self.shell(f"rm {self._recording_path}")
            if os.path.exists(local_path):
                os.unlink(local_path)
            self._recording_process = None
            self._recording_path = None

        return data

    async def get_logcat(
        self,
        lines: int = 100,
        tag: Optional[str] = None,
        level: Optional[str] = None,
        since: Optional[str] = None,
        clear: bool = False,
    ) -> str:
        """Get logcat output.

        Args:
            lines: Number of lines to return
            tag: Filter by tag
            level: Minimum level (V, D, I, W, E, F)
            since: Logs since timestamp
            clear: Clear the buffer after reading

        Returns:
            Log output
        """
        if clear:
            await self.shell("logcat -c")

        cmd_parts = ["logcat", "-d", f"-t {lines}"]

        if since:
            cmd_parts.append(f"-T '{since}'")

        if tag and level:
            cmd_parts.append(f"{tag}:{level} *:S")
        elif tag:
            cmd_parts.append(f"{tag}:V *:S")
        elif level:
            cmd_parts.append(f"*:{level}")

        result = await self.shell(" ".join(cmd_parts), timeout=10.0)
        return result.stdout

    async def get_current_activity(self) -> dict:
        """Get the current foreground activity.

        Tries multiple methods to handle different Android versions:
        1. dumpsys activity activities with mResumedActivity (older Android)
        2. dumpsys activity activities with topResumedActivity (newer Android)
        3. dumpsys window with mCurrentFocus (fallback)
        """
        # Method 1: Try mResumedActivity (works on most versions)
        result = await self.shell(
            "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity'"
        )

        if result.success and result.stdout.strip():
            # Parse formats like:
            # mResumedActivity: ActivityRecord{xxx u0 com.app/.MainActivity t123}
            # topResumedActivity=ActivityRecord{xxx u0 com.app/.Activity t123}
            # Look for package/activity pattern
            match = re.search(
                r"([a-zA-Z][a-zA-Z0-9_.]*)/([a-zA-Z0-9_.]+)", result.stdout
            )
            if match:
                return {"package": match.group(1), "activity": match.group(2)}

        # Method 2: Try dumpsys window mCurrentFocus
        result = await self.shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")

        if result.success and result.stdout.strip():
            # Parse format: mCurrentFocus=Window{xxx u0 com.app/com.app.MainActivity}
            # or mFocusedApp=ActivityRecord{xxx u0 com.app/.MainActivity t123}
            match = re.search(
                r"([a-zA-Z][a-zA-Z0-9_.]*)/([a-zA-Z0-9_.]+)", result.stdout
            )
            if match:
                return {"package": match.group(1), "activity": match.group(2)}

        # Method 3: Use am stack list (Android 10+)
        result = await self.shell("am stack list 2>/dev/null | head -5")
        if result.success and result.stdout.strip():
            match = re.search(
                r"([a-zA-Z][a-zA-Z0-9_.]*)/([a-zA-Z0-9_.]+)", result.stdout
            )
            if match:
                return {"package": match.group(1), "activity": match.group(2)}

        return {"package": "unknown", "activity": "unknown"}

    async def get_current_package(self) -> str:
        """Get the current foreground package."""
        activity = await self.get_current_activity()
        return activity.get("package", "unknown")

    async def install_apk(self, local_path: str, replace: bool = True) -> CommandResult:
        """Install an APK file."""
        # Validate path to prevent path traversal
        resolved_path = os.path.realpath(local_path)
        if not os.path.isfile(resolved_path):
            raise ADBError(f"APK file not found: {local_path}")

        args = ["install"]
        if replace:
            args.append("-r")
        args.append(resolved_path)

        return await self.run(*args, timeout=120.0)

    async def uninstall_app(self, package: str, keep_data: bool = False) -> CommandResult:
        """Uninstall an app."""
        # Validate package name format
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_.]*$", package):
            raise ADBError(f"Invalid package name format: {package}")

        args = ["uninstall"]
        if keep_data:
            args.append("-k")
        args.append(package)

        return await self.run(*args)

    async def launch_app(
        self, package: str, activity: Optional[str] = None, wait: bool = True
    ) -> CommandResult:
        """Launch an app."""
        # Validate package name format
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_.]*$", package):
            raise ADBError(f"Invalid package name format: {package}")

        if activity:
            component = f"{package}/{activity}"
        else:
            # Find the launcher activity
            result = await self.shell(
                f"cmd package resolve-activity --brief {package} | tail -n 1"
            )
            if result.success and "/" in result.stdout:
                component = result.stdout.strip()
            else:
                # Fallback: try monkey
                return await self.shell(
                    f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
                )

        cmd = "am start"
        if wait:
            cmd += " -W"
        cmd += f" -n {component}"

        return await self.shell(cmd)

    async def stop_app(self, package: str) -> CommandResult:
        """Force stop an app."""
        # Validate package name format
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_.]*$", package):
            raise ADBError(f"Invalid package name format: {package}")
        return await self.shell(f"am force-stop {package}")

    async def clear_app_data(self, package: str) -> CommandResult:
        """Clear app data and cache."""
        # Validate package name format
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_.]*$", package):
            raise ADBError(f"Invalid package name format: {package}")
        return await self.shell(f"pm clear {package}")

    async def list_packages(
        self, filter_type: Optional[str] = None, filter_text: Optional[str] = None
    ) -> list[str]:
        """List installed packages."""
        cmd = "pm list packages"

        if filter_type == "system":
            cmd += " -s"
        elif filter_type == "third-party":
            cmd += " -3"

        result = await self.shell(cmd)
        if not result.success:
            return []

        packages = []
        for line in result.stdout.split("\n"):
            if line.startswith("package:"):
                pkg = line[8:].strip()
                if filter_text is None or filter_text.lower() in pkg.lower():
                    packages.append(pkg)

        return sorted(packages)

    async def get_app_info(self, package: str) -> dict:
        """Get detailed app information."""
        # Validate package name format
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_.]*$", package):
            raise ADBError(f"Invalid package name format: {package}")

        result = await self.shell(f"dumpsys package {package}")
        if not result.success:
            raise ADBError(f"Failed to get app info: {result.stderr}")

        info = {"package": package}

        # Parse version
        match = re.search(r"versionName=(\S+)", result.stdout)
        if match:
            info["version_name"] = match.group(1)

        match = re.search(r"versionCode=(\d+)", result.stdout)
        if match:
            info["version_code"] = int(match.group(1))

        # Parse permissions
        permissions = []
        in_permissions = False
        for line in result.stdout.split("\n"):
            if "requested permissions:" in line.lower():
                in_permissions = True
            elif in_permissions:
                if line.strip().startswith("android.permission."):
                    permissions.append(line.strip())
                elif not line.strip().startswith("android."):
                    break

        info["permissions"] = permissions

        return info
