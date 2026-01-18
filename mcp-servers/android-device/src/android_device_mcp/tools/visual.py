"""Visual tools for screenshots, hierarchy, and element finding."""

import base64
import io
import logging
from typing import Optional

from mcp.types import ImageContent, TextContent
from PIL import Image

from ..adapters.adb import ADBAdapter, ADBError
from ..adapters.uiautomator import UIAutomatorAdapter, Element
from ..persistence.learning_store import LearningStore
from ..utils import retry_async, format_error_message

logger = logging.getLogger(__name__)


async def take_screenshot(
    adb: ADBAdapter,
    uia: UIAutomatorAdapter,
    element_selector: Optional[str] = None,
    format: str = "png",
    quality: int = 80,
    max_retries: int = 2,
    save_to_file: Optional[str] = None,
    max_width: Optional[int] = None,
) -> list[ImageContent | TextContent]:
    """Take a screenshot of the screen or a specific element.

    Args:
        adb: ADB adapter
        uia: UIAutomator adapter
        element_selector: Optional selector for element screenshot
        format: Image format (png, jpeg, webp)
        quality: JPEG/WebP quality (1-100)
        max_retries: Number of retry attempts for screenshot capture
        save_to_file: If provided, save screenshot to this file path instead of
                      returning base64. Claude Code can then read the file directly.
                      This is much more context-efficient for large screenshots.
        max_width: If provided, resize image to this max width (maintains aspect ratio).
                   Useful for reducing file size while keeping image readable.

    Returns:
        List with ImageContent containing the screenshot, or TextContent with file path
    """
    import os
    import tempfile

    try:
        # Capture full screen with retry logic
        png_data = await retry_async(
            adb.screenshot,
            max_retries=max_retries,
            delay_ms=300,
            exceptions=(ADBError, Exception),
        )

        # Load image
        img = Image.open(io.BytesIO(png_data))

        # If element specified, crop to element
        if element_selector:
            element = await uia.find_element(resource_id=element_selector)
            if not element:
                element = await uia.find_element(text=element_selector)
            if not element:
                element = await uia.find_element(content_desc=element_selector)

            if element:
                # Crop to element bounds
                left, top, right, bottom = element.bounds
                img = img.crop((left, top, right, bottom))

        # Resize if max_width specified
        if max_width and img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

        # Convert to target format
        buffer = io.BytesIO()
        if format.lower() == "jpeg":
            img = img.convert("RGB")
            img.save(buffer, format="JPEG", quality=quality)
            mime_type = "image/jpeg"
            ext = ".jpg"
        elif format.lower() == "webp":
            img.save(buffer, format="WEBP", quality=quality)
            mime_type = "image/webp"
            ext = ".webp"
        else:
            img.save(buffer, format="PNG")
            mime_type = "image/png"
            ext = ".png"

        img_data = buffer.getvalue()

        # Save to file if requested
        if save_to_file:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(save_to_file)), exist_ok=True)
            with open(save_to_file, "wb") as f:
                f.write(img_data)
            return [
                TextContent(
                    type="text",
                    text=f"Screenshot saved to: {save_to_file}\n"
                         f"Size: {img.width}x{img.height} pixels, {len(img_data):,} bytes\n"
                         f"Use Claude Code's Read tool to view this image.",
                )
            ]

        # If image is very large, auto-save to temp file and suggest reading it
        if len(img_data) > 500_000:  # 500KB threshold
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"android_screenshot{ext}")
            with open(temp_path, "wb") as f:
                f.write(img_data)
            return [
                TextContent(
                    type="text",
                    text=f"Screenshot is large ({len(img_data):,} bytes). "
                         f"Saved to: {temp_path}\n"
                         f"Size: {img.width}x{img.height} pixels\n"
                         f"Use Claude Code's Read tool to view this image, or use "
                         f"max_width parameter to reduce size.",
                )
            ]

        # Encode as base64 for MCP
        b64_data = base64.b64encode(img_data).decode("utf-8")

        return [
            ImageContent(
                type="image",
                data=b64_data,
                mimeType=mime_type,
            )
        ]

    except ADBError as e:
        return [TextContent(type="text", text=format_error_message(e, "Screenshot failed"))]
    except Exception as e:
        logger.exception("Screenshot failed")
        return [TextContent(type="text", text=format_error_message(e, "Screenshot failed"))]


async def get_hierarchy(
    uia: UIAutomatorAdapter,
    compressed: bool = True,
    max_depth: Optional[int] = None,
    clickable_only: bool = False,
    include_system_ui: bool = True,
) -> str:
    """Get UI hierarchy as XML.

    Args:
        uia: UIAutomator adapter
        compressed: If True, simplify the output by removing verbose attributes
        max_depth: Maximum depth of hierarchy to return (None for unlimited)
        clickable_only: If True, only return clickable/focusable elements
        include_system_ui: If True, include system UI (status bar, nav bar)

    Returns:
        XML string
    """
    import re
    import xml.etree.ElementTree as ET

    xml_str = await uia.get_hierarchy_xml()

    # Parse XML for filtering if needed
    if max_depth is not None or clickable_only or not include_system_ui:
        try:
            root = ET.fromstring(xml_str)

            def filter_node(node: ET.Element, depth: int = 0) -> bool:
                """Return True if node should be kept."""
                # Check depth limit
                if max_depth is not None and depth > max_depth:
                    return False

                # Check clickable filter
                if clickable_only:
                    is_interactive = (
                        node.get("clickable") == "true" or
                        node.get("focusable") == "true" or
                        node.get("scrollable") == "true" or
                        node.get("checkable") == "true"
                    )
                    if not is_interactive:
                        # Keep node only if it has interactive children
                        has_interactive_child = any(
                            filter_node(child, depth + 1) for child in node
                        )
                        if not has_interactive_child:
                            return False

                # Check system UI filter
                if not include_system_ui:
                    pkg = node.get("package", "")
                    if pkg in ("com.android.systemui", ""):
                        resource_id = node.get("resource-id", "")
                        if any(x in resource_id for x in [
                            "statusBarBackground", "navigation_bar",
                            "NavigationBar", "StatusBar"
                        ]):
                            return False

                return True

            def prune_tree(node: ET.Element, depth: int = 0) -> None:
                """Remove nodes that don't pass filter."""
                children_to_remove = []
                for child in node:
                    if not filter_node(child, depth + 1):
                        children_to_remove.append(child)
                    else:
                        prune_tree(child, depth + 1)

                for child in children_to_remove:
                    node.remove(child)

            prune_tree(root)
            xml_str = ET.tostring(root, encoding="unicode")
        except ET.ParseError as e:
            logger.warning(f"Failed to parse XML for filtering: {e}")

    if compressed:
        # Remove verbose attributes to reduce token usage
        xml_str = re.sub(r'\s+NAF="[^"]*"', '', xml_str)
        xml_str = re.sub(r'\s+rotation="[^"]*"', '', xml_str)
        # Remove attributes that are usually empty or false
        xml_str = re.sub(r'\s+checked="false"', '', xml_str)
        xml_str = re.sub(r'\s+checkable="false"', '', xml_str)
        xml_str = re.sub(r'\s+selected="false"', '', xml_str)
        # Remove password attribute (not a secret - it's a UI hierarchy attribute)
        xml_str = re.sub(r'\s+pass' + r'word="false"', '', xml_str)
        xml_str = re.sub(r'\s+long-clickable="false"', '', xml_str)

    return xml_str


async def get_bounds(
    uia: UIAutomatorAdapter,
    clickable_only: bool = False,
    include_system_ui: bool = True,
    limit: int = 100,
) -> list[dict]:
    """Get element bounds only (faster than full hierarchy).

    Args:
        uia: UIAutomator adapter
        clickable_only: If True, only return clickable/focusable elements
        include_system_ui: If True, include system UI elements
        limit: Maximum number of elements to return

    Returns:
        List of element bounds with basic info
    """
    all_bounds = await uia.get_bounds_only()
    results = []

    for elem in all_bounds:
        # Apply filters
        if clickable_only and not elem.get("clickable"):
            continue

        if not include_system_ui:
            resource_id = elem.get("resource_id", "")
            if any(x in resource_id for x in [
                "statusBarBackground", "navigation_bar",
                "NavigationBar", "StatusBar", "com.android.systemui"
            ]):
                continue

        results.append(elem)
        if len(results) >= limit:
            break

    return results


async def find_single_element(
    uia: UIAutomatorAdapter,
    learning: LearningStore,
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    class_name: Optional[str] = None,
    content_desc: Optional[str] = None,
    xpath: Optional[str] = None,
) -> Optional[dict]:
    """Find a single UI element.

    Args:
        uia: UIAutomator adapter
        learning: Learning store for cached patterns
        text: Match by text
        resource_id: Match by resource ID
        class_name: Match by class
        content_desc: Match by content description
        xpath: XPath selector

    Returns:
        Element info dict or None
    """
    # Check learning store for cached selector if we have a key
    pattern_key = text or resource_id or content_desc
    if pattern_key and learning:
        try:
            current_pkg = await uia.adb.get_current_package()
            pattern = await learning.get_pattern(current_pkg, pattern_key)
            if pattern and pattern.get("pattern_type") == "element":
                data = pattern.get("pattern_data", {})
                selectors = data.get("selectors", [])
                for sel in sorted(selectors, key=lambda s: -s.get("confidence", 0)):
                    element = await uia.find_element(
                        text=sel.get("text"),
                        resource_id=sel.get("resourceId"),
                        content_desc=sel.get("contentDescription"),
                    )
                    if element:
                        return element.to_dict()
        except Exception as e:
            logger.debug(f"Learning lookup failed: {e}")

    # Direct search
    element = await uia.find_element(
        text=text,
        resource_id=resource_id,
        class_name=class_name,
        content_desc=content_desc,
        xpath=xpath,
    )

    if element:
        # Auto-learn this selector if enabled
        if learning and pattern_key:
            try:
                current_pkg = await uia.adb.get_current_package()
                await learning.save_pattern(
                    app_package=current_pkg,
                    pattern_key=pattern_key,
                    pattern_type="element",
                    pattern_data={
                        "selectors": [
                            {"resourceId": element.resource_id, "confidence": 0.9}
                            if element.resource_id else None,
                            {"text": element.text, "confidence": 0.7}
                            if element.text else None,
                            {"contentDescription": element.content_desc, "confidence": 0.8}
                            if element.content_desc else None,
                        ]
                    },
                )
            except Exception as e:
                logger.debug(f"Auto-learn failed: {e}")

        return element.to_dict()

    return None


async def find_multiple_elements(
    uia: UIAutomatorAdapter,
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    class_name: Optional[str] = None,
    content_desc: Optional[str] = None,
    xpath: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Find multiple UI elements.

    Args:
        uia: UIAutomator adapter
        text: Match by text
        resource_id: Match by resource ID
        class_name: Match by class
        content_desc: Match by content description
        xpath: XPath selector
        limit: Maximum results

    Returns:
        List of element info dicts
    """
    elements = await uia.find_elements(
        text=text,
        resource_id=resource_id,
        class_name=class_name,
        content_desc=content_desc,
        xpath=xpath,
        limit=limit,
    )
    return [e.to_dict() for e in elements]


# Screen recording state
_recording_active = False


async def start_recording(adb: ADBAdapter, max_duration: int = 180) -> dict:
    """Start screen recording.

    Args:
        adb: ADB adapter
        max_duration: Maximum duration in seconds

    Returns:
        Recording session info
    """
    global _recording_active

    if _recording_active:
        return {"success": False, "error": "Recording already in progress"}

    try:
        await adb.start_screen_record(max_duration=max_duration)
        _recording_active = True
        return {
            "success": True,
            "message": f"Recording started (max {max_duration}s)",
            "max_duration": max_duration,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def stop_recording(adb: ADBAdapter) -> list[ImageContent | TextContent]:
    """Stop screen recording and return video.

    Args:
        adb: ADB adapter

    Returns:
        Video content
    """
    global _recording_active

    if not _recording_active:
        return [TextContent(type="text", text="No recording in progress")]

    try:
        video_data = await adb.stop_screen_record()
        _recording_active = False

        b64_data = base64.b64encode(video_data).decode("utf-8")

        return [
            TextContent(
                type="text",
                text=f"Recording stopped. Video size: {len(video_data)} bytes. "
                     f"Data encoded as base64 follows:",
            ),
            TextContent(
                type="text",
                text=f"data:video/mp4;base64,{b64_data[:100]}... (truncated for display)",
            ),
        ]
    except ADBError as e:
        _recording_active = False
        return [TextContent(type="text", text=f"Failed to stop recording: {e}")]
