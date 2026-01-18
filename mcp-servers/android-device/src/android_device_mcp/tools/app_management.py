"""App management tools for install, launch, stop, and info."""

import logging
import os
from typing import Optional

from ..adapters.adb import ADBAdapter, ADBError

logger = logging.getLogger(__name__)


async def install_application(
    adb: ADBAdapter,
    apk_path: str,
    replace: bool = True,
) -> dict:
    """Install an APK file.

    Args:
        adb: ADB adapter
        apk_path: Path to APK
        replace: Replace if exists

    Returns:
        Installation result
    """
    # Validate path
    if not os.path.isfile(apk_path):
        return {"success": False, "error": f"APK file not found: {apk_path}"}

    if not apk_path.endswith(".apk"):
        return {"success": False, "error": "File must have .apk extension"}

    try:
        result = await adb.install_apk(apk_path, replace)
        return {
            "success": result.success,
            "message": "Installation successful" if result.success else "Installation failed",
            "output": result.stdout,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def uninstall_application(
    adb: ADBAdapter,
    package: str,
    keep_data: bool = False,
) -> dict:
    """Uninstall an app.

    Args:
        adb: ADB adapter
        package: Package name
        keep_data: Keep app data

    Returns:
        Uninstall result
    """
    try:
        result = await adb.uninstall_app(package, keep_data)
        return {
            "success": result.success,
            "package": package,
            "kept_data": keep_data,
            "output": result.stdout,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def launch_application(
    adb: ADBAdapter,
    package: str,
    activity: Optional[str] = None,
    wait: bool = True,
) -> dict:
    """Launch an app.

    Args:
        adb: ADB adapter
        package: Package name
        activity: Specific activity
        wait: Wait for launch

    Returns:
        Launch result
    """
    try:
        result = await adb.launch_app(package, activity, wait)
        return {
            "success": result.success,
            "package": package,
            "activity": activity,
            "output": result.stdout,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def stop_application(adb: ADBAdapter, package: str) -> dict:
    """Force stop an app.

    Args:
        adb: ADB adapter
        package: Package name

    Returns:
        Stop result
    """
    try:
        result = await adb.stop_app(package)
        return {
            "success": result.success,
            "package": package,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def clear_application_data(adb: ADBAdapter, package: str) -> dict:
    """Clear app data and cache.

    Args:
        adb: ADB adapter
        package: Package name

    Returns:
        Clear result
    """
    try:
        result = await adb.clear_app_data(package)
        return {
            "success": result.success,
            "package": package,
            "output": result.stdout,
            "error": result.stderr if not result.success else None,
        }
    except ADBError as e:
        return {"success": False, "error": str(e)}


async def list_installed_packages(
    adb: ADBAdapter,
    filter_type: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> list[str]:
    """List installed packages.

    Args:
        adb: ADB adapter
        filter_type: 'system' or 'third-party'
        filter_text: Name filter

    Returns:
        List of package names
    """
    try:
        return await adb.list_packages(filter_type, filter_text)
    except ADBError:
        return []


async def get_application_info(adb: ADBAdapter, package: str) -> dict:
    """Get detailed app information.

    Args:
        adb: ADB adapter
        package: Package name

    Returns:
        App info dict
    """
    try:
        return await adb.get_app_info(package)
    except ADBError as e:
        return {"error": str(e)}
