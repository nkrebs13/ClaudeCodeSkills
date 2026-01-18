"""UIAutomator2 adapter for UI element interaction."""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Optional

from .adb import ADBAdapter, ADBError

logger = logging.getLogger(__name__)


@dataclass
class Element:
    """UI element representation."""

    text: str
    resource_id: str
    class_name: str
    content_desc: str
    bounds: tuple[int, int, int, int]  # left, top, right, bottom
    checkable: bool
    checked: bool
    clickable: bool
    enabled: bool
    focusable: bool
    focused: bool
    scrollable: bool
    selected: bool
    index: int
    package: str

    @property
    def center(self) -> tuple[int, int]:
        """Get center coordinates."""
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "text": self.text,
            "resource_id": self.resource_id,
            "class_name": self.class_name,
            "content_desc": self.content_desc,
            "bounds": {
                "left": self.bounds[0],
                "top": self.bounds[1],
                "right": self.bounds[2],
                "bottom": self.bounds[3],
            },
            "center": {"x": self.center[0], "y": self.center[1]},
            "width": self.width,
            "height": self.height,
            "clickable": self.clickable,
            "enabled": self.enabled,
            "scrollable": self.scrollable,
            "package": self.package,
        }


class UIAutomatorAdapter:
    """Adapter for UI element interaction using uiautomator.

    This adapter provides two modes:
    1. Pure ADB mode: Uses `uiautomator dump` for hierarchy
    2. Python uiautomator2 mode: Uses the uiautomator2 library for richer features

    The adapter automatically falls back to ADB mode if uiautomator2 is not available.
    """

    def __init__(self, adb: ADBAdapter, use_python_u2: bool = True):
        """Initialize UIAutomator adapter.

        Args:
            adb: ADB adapter for device communication
            use_python_u2: Try to use python uiautomator2 library if available
        """
        self.adb = adb
        self._u2_device: Any = None
        self._use_python_u2 = use_python_u2
        self._u2_available: Optional[bool] = None

    async def _get_u2_device(self) -> Any:
        """Get or create uiautomator2 device connection."""
        if self._u2_device is not None:
            return self._u2_device

        if not self._use_python_u2:
            return None

        try:
            import uiautomator2 as u2

            serial = await self.adb.get_device_serial()
            # uiautomator2 connect is sync, run in executor
            loop = asyncio.get_event_loop()
            self._u2_device = await loop.run_in_executor(None, u2.connect, serial)
            self._u2_available = True
            logger.info("Connected to device via uiautomator2")
            return self._u2_device
        except ImportError:
            logger.info("uiautomator2 not installed, using ADB fallback")
            self._u2_available = False
            return None
        except Exception as e:
            logger.warning(f"Failed to connect via uiautomator2: {e}, using ADB fallback")
            self._u2_available = False
            return None

    async def get_hierarchy_xml(self) -> str:
        """Get UI hierarchy as XML string."""
        # Try uiautomator2 first
        device = await self._get_u2_device()
        if device:
            try:
                loop = asyncio.get_event_loop()
                xml_str = await loop.run_in_executor(None, device.dump_hierarchy)
                return xml_str
            except Exception as e:
                logger.warning(f"uiautomator2 dump failed: {e}, falling back to ADB")

        # ADB fallback
        result = await self.adb.shell("uiautomator dump /dev/tty")
        if not result.success:
            raise ADBError(f"Failed to dump UI hierarchy: {result.stderr}")

        # Extract XML from output (may have prefix text)
        xml_start = result.stdout.find("<?xml")
        if xml_start == -1:
            xml_start = result.stdout.find("<hierarchy")
        if xml_start == -1:
            raise ADBError(f"No XML found in hierarchy dump: {result.stdout[:200]}")

        return result.stdout[xml_start:]

    def _parse_bounds(self, bounds_str: str) -> tuple[int, int, int, int]:
        """Parse bounds string like '[0,0][1080,1920]' to tuple."""
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
        if not match:
            return (0, 0, 0, 0)
        return (int(match.group(1)), int(match.group(2)),
                int(match.group(3)), int(match.group(4)))

    def _parse_element(self, node: ET.Element) -> Element:
        """Parse XML node to Element."""
        return Element(
            text=node.get("text", ""),
            resource_id=node.get("resource-id", ""),
            class_name=node.get("class", ""),
            content_desc=node.get("content-desc", ""),
            bounds=self._parse_bounds(node.get("bounds", "[0,0][0,0]")),
            checkable=node.get("checkable", "false") == "true",
            checked=node.get("checked", "false") == "true",
            clickable=node.get("clickable", "false") == "true",
            enabled=node.get("enabled", "true") == "true",
            focusable=node.get("focusable", "false") == "true",
            focused=node.get("focused", "false") == "true",
            scrollable=node.get("scrollable", "false") == "true",
            selected=node.get("selected", "false") == "true",
            index=int(node.get("index", "0")),
            package=node.get("package", ""),
        )

    async def get_all_elements(self) -> list[Element]:
        """Get all UI elements from hierarchy."""
        xml_str = await self.get_hierarchy_xml()
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            raise ADBError(f"Failed to parse UI hierarchy XML: {e}")

        elements = []
        for node in root.iter("node"):
            elements.append(self._parse_element(node))
        return elements

    async def get_bounds_only(self) -> list[dict]:
        """Get just the bounds of all elements (faster than full parse)."""
        elements = await self.get_all_elements()
        return [
            {
                "text": e.text[:50] if e.text else "",
                "resource_id": e.resource_id,
                "bounds": {
                    "left": e.bounds[0],
                    "top": e.bounds[1],
                    "right": e.bounds[2],
                    "bottom": e.bounds[3],
                },
                "clickable": e.clickable,
            }
            for e in elements
            if e.bounds[2] > e.bounds[0] and e.bounds[3] > e.bounds[1]  # Has size
        ]

    async def find_element(
        self,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        class_name: Optional[str] = None,
        content_desc: Optional[str] = None,
        xpath: Optional[str] = None,
    ) -> Optional[Element]:
        """Find first matching element."""
        elements = await self.find_elements(
            text=text,
            resource_id=resource_id,
            class_name=class_name,
            content_desc=content_desc,
            xpath=xpath,
            limit=1,
        )
        return elements[0] if elements else None

    async def find_elements(
        self,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        class_name: Optional[str] = None,
        content_desc: Optional[str] = None,
        xpath: Optional[str] = None,
        limit: int = 50,
    ) -> list[Element]:
        """Find all matching elements."""
        # Try uiautomator2 for better selectors
        device = await self._get_u2_device()
        if device and not xpath:  # u2 handles basic selectors well
            try:
                loop = asyncio.get_event_loop()

                def u2_find() -> list:
                    selector_kwargs = {}
                    if text:
                        selector_kwargs["text"] = text
                    if resource_id:
                        selector_kwargs["resourceId"] = resource_id
                    if class_name:
                        selector_kwargs["className"] = class_name
                    if content_desc:
                        selector_kwargs["description"] = content_desc

                    if not selector_kwargs:
                        return []

                    results = []
                    for elem in device(**selector_kwargs):
                        info = elem.info
                        results.append(Element(
                            text=info.get("text", ""),
                            resource_id=info.get("resourceId", ""),
                            class_name=info.get("className", ""),
                            content_desc=info.get("contentDescription", ""),
                            bounds=(
                                info["bounds"]["left"],
                                info["bounds"]["top"],
                                info["bounds"]["right"],
                                info["bounds"]["bottom"],
                            ),
                            checkable=info.get("checkable", False),
                            checked=info.get("checked", False),
                            clickable=info.get("clickable", False),
                            enabled=info.get("enabled", True),
                            focusable=info.get("focusable", False),
                            focused=info.get("focused", False),
                            scrollable=info.get("scrollable", False),
                            selected=info.get("selected", False),
                            index=0,
                            package=info.get("packageName", ""),
                        ))
                        if len(results) >= limit:
                            break
                    return results

                return await loop.run_in_executor(None, u2_find)
            except Exception as e:
                logger.warning(f"uiautomator2 find failed: {e}, falling back to XML parse")

        # XML-based search
        xml_str = await self.get_hierarchy_xml()
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            raise ADBError(f"Failed to parse UI hierarchy: {e}")

        results = []

        if xpath:
            # XPath search - ET.findall needs relative paths, not absolute
            # Convert absolute paths like "//*[@focused='true']" to ".//..."
            search_path = xpath
            if search_path.startswith("//"):
                search_path = "." + search_path
            elif search_path.startswith("/"):
                search_path = "." + search_path
            for node in root.findall(search_path):
                results.append(self._parse_element(node))
                if len(results) >= limit:
                    break
        else:
            # Attribute matching
            for node in root.iter("node"):
                matches = True

                if text and node.get("text", "") != text:
                    # Try contains match
                    if text not in node.get("text", ""):
                        matches = False
                if resource_id and resource_id not in node.get("resource-id", ""):
                    matches = False
                if class_name and class_name != node.get("class", ""):
                    matches = False
                if content_desc and content_desc not in node.get("content-desc", ""):
                    matches = False

                if matches and (text or resource_id or class_name or content_desc):
                    results.append(self._parse_element(node))
                    if len(results) >= limit:
                        break

        return results

    async def click(self, x: int, y: int) -> bool:
        """Click at coordinates using uiautomator2 or ADB."""
        device = await self._get_u2_device()
        if device:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, device.click, x, y)
                return True
            except Exception:
                pass

        # ADB fallback
        result = await self.adb.tap(x, y)
        return result.success

    async def click_element(self, element: Element) -> bool:
        """Click on an element's center."""
        x, y = element.center
        return await self.click(x, y)

    async def long_click(self, x: int, y: int, duration: float = 1.0) -> bool:
        """Long click at coordinates."""
        device = await self._get_u2_device()
        if device:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, device.long_click, x, y, duration)
                return True
            except Exception:
                pass

        # ADB fallback
        result = await self.adb.long_press(x, y, int(duration * 1000))
        return result.success

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3
    ) -> bool:
        """Swipe from (x1,y1) to (x2,y2)."""
        device = await self._get_u2_device()
        if device:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, device.swipe, x1, y1, x2, y2, duration)
                return True
            except Exception:
                pass

        # ADB fallback
        result = await self.adb.swipe(x1, y1, x2, y2, int(duration * 1000))
        return result.success

    async def pinch(
        self, center_x: int, center_y: int, zoom_in: bool = True, scale: float = 0.5
    ) -> bool:
        """Pinch zoom gesture."""
        device = await self._get_u2_device()
        if device:
            try:
                loop = asyncio.get_event_loop()
                if zoom_in:
                    await loop.run_in_executor(
                        None, lambda: device.pinch_in(percent=int(scale * 100))
                    )
                else:
                    await loop.run_in_executor(
                        None, lambda: device.pinch_out(percent=int(scale * 100))
                    )
                return True
            except Exception as e:
                logger.warning(f"Pinch failed: {e}")
                return False

        # No ADB fallback for pinch - requires multi-touch
        raise ADBError("Pinch gesture requires uiautomator2 library")

    async def set_text(self, text: str, clear_first: bool = True) -> bool:
        """Set text in focused field."""
        device = await self._get_u2_device()
        if device:
            try:
                loop = asyncio.get_event_loop()
                if clear_first:
                    await loop.run_in_executor(None, device.clear_text)
                await loop.run_in_executor(None, device.send_keys, text)
                return True
            except Exception:
                pass

        # ADB fallback
        if clear_first:
            # Select all and delete
            await self.adb.shell("input keyevent KEYCODE_CTRL_LEFT KEYCODE_A")
            await self.adb.shell("input keyevent KEYCODE_DEL")

        result = await self.adb.type_text(text)
        return result.success

    async def wait_for_idle(self, timeout_ms: int = 5000) -> bool:
        """Wait for UI to become idle."""
        device = await self._get_u2_device()
        if device:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, lambda: device.wait_activity(timeout=timeout_ms / 1000)
                )
                return True
            except Exception:
                pass

        # ADB fallback - just wait a bit
        await asyncio.sleep(0.5)
        return True

    async def wait_for_element(
        self,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        timeout_ms: int = 10000,
        poll_interval_ms: int = 500,
    ) -> Optional[Element]:
        """Wait for element to appear."""
        device = await self._get_u2_device()
        if device:
            try:
                loop = asyncio.get_event_loop()

                def u2_wait() -> Optional[Element]:
                    selector_kwargs = {}
                    if text:
                        selector_kwargs["text"] = text
                    if resource_id:
                        selector_kwargs["resourceId"] = resource_id

                    if device(**selector_kwargs).wait(timeout=timeout_ms / 1000):
                        info = device(**selector_kwargs).info
                        return Element(
                            text=info.get("text", ""),
                            resource_id=info.get("resourceId", ""),
                            class_name=info.get("className", ""),
                            content_desc=info.get("contentDescription", ""),
                            bounds=(
                                info["bounds"]["left"],
                                info["bounds"]["top"],
                                info["bounds"]["right"],
                                info["bounds"]["bottom"],
                            ),
                            checkable=info.get("checkable", False),
                            checked=info.get("checked", False),
                            clickable=info.get("clickable", False),
                            enabled=info.get("enabled", True),
                            focusable=info.get("focusable", False),
                            focused=info.get("focused", False),
                            scrollable=info.get("scrollable", False),
                            selected=info.get("selected", False),
                            index=0,
                            package=info.get("packageName", ""),
                        )
                    return None

                return await loop.run_in_executor(None, u2_wait)
            except Exception as e:
                logger.warning(f"uiautomator2 wait failed: {e}, falling back to polling")

        # Polling fallback
        elapsed = 0
        while elapsed < timeout_ms:
            element = await self.find_element(text=text, resource_id=resource_id)
            if element:
                return element
            await asyncio.sleep(poll_interval_ms / 1000)
            elapsed += poll_interval_ms

        return None
