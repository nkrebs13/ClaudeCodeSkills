"""Configuration for Android Device MCP Server."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """User-controllable configuration flags."""

    # Performance vs Quality tradeoffs
    screenshot_quality: int = 80  # 1-100, affects file size
    screenshot_format: str = "png"  # png|jpeg|webp
    prefer_scrcpy: bool = True  # False = always use ADB (slower but simpler)
    parallel_commands: bool = True  # Batch ADB operations

    # Learning behavior
    learning_enabled: bool = True  # Master switch
    auto_learn_elements: bool = True  # Store found elements automatically
    pattern_staleness_days: int = 30  # After this, reduce confidence
    max_patterns_per_app: int = 1000  # Prevent unbounded growth

    # Context/token tradeoffs
    verbose_errors: bool = True  # Detailed vs terse error messages
    include_layout_in_screenshot: bool = False  # Overlay element bounds
    logcat_default_lines: int = 100  # Default log lines to return

    # Device connection
    default_device: str = ""  # If empty, use first connected
    connection_timeout: int = 5000  # ms

    # Security
    allow_shell_commands: bool = True  # If False, block raw shell access
    shell_command_allowlist: list[str] = field(default_factory=list)

    # Paths
    learning_db_path: Optional[Path] = None  # If None, use default location
    scrcpy_path: Optional[Path] = None  # Path to scrcpy binary

    def __post_init__(self) -> None:
        """Set default paths after initialization."""
        if self.learning_db_path is None:
            # Default to user's data directory
            data_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            self.learning_db_path = data_dir / "android-device-mcp" / "learning.db"

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        config = cls()

        # Override from environment
        if val := os.environ.get("ANDROID_MCP_SCREENSHOT_QUALITY"):
            config.screenshot_quality = int(val)
        if val := os.environ.get("ANDROID_MCP_SCREENSHOT_FORMAT"):
            config.screenshot_format = val
        if val := os.environ.get("ANDROID_MCP_PREFER_SCRCPY"):
            config.prefer_scrcpy = val.lower() in ("true", "1", "yes")
        if val := os.environ.get("ANDROID_MCP_LEARNING_ENABLED"):
            config.learning_enabled = val.lower() in ("true", "1", "yes")
        if val := os.environ.get("ANDROID_MCP_DEFAULT_DEVICE"):
            config.default_device = val
        if val := os.environ.get("ANDROID_MCP_ALLOW_SHELL"):
            config.allow_shell_commands = val.lower() in ("true", "1", "yes")
        if val := os.environ.get("ANDROID_MCP_DB_PATH"):
            config.learning_db_path = Path(val)
        if val := os.environ.get("ANDROID_MCP_SCRCPY_PATH"):
            config.scrcpy_path = Path(val)

        return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set the global config instance."""
    global _config
    _config = config
