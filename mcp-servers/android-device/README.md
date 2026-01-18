# Android Device MCP Server

MCP server for Android device interaction - screenshots, automation, debugging, and more.

## Features

- **30+ Tools**: Screenshots, element finding, touch interactions, app management, logging
- **Fast Screenshots**: Uses ADB exec-out for low-latency capture
- **Element Detection**: UIAutomator2 accessibility trees for reliable element finding
- **Learning System**: SQLite-backed pattern storage that improves over time
- **Zero Dependencies**: Everything runs locally, no cloud services required

## Installation

### Prerequisites

1. **ADB**: Install Android SDK Platform Tools
   ```bash
   # macOS
   brew install android-platform-tools

   # Linux
   sudo apt install android-tools-adb

   # Or download from: https://developer.android.com/tools/releases/platform-tools
   ```

2. **Python 3.10+**

### Install the MCP Server

```bash
# Clone the repository
git clone https://github.com/nathankrebs/ClaudeCodeSkills.git
cd ClaudeCodeSkills/mcp-servers/android-device

# Install in development mode
pip install -e .

# Or install dependencies directly
pip install -e ".[dev]"  # Include dev dependencies
```

### Configure Claude Code

**Recommended: Project-level configuration**

Create a `.mcp.json` file in your Android project root:

```json
{
  "mcpServers": {
    "android-device": {
      "command": "android-device-mcp",
      "args": []
    }
  }
}
```

This approach:
- Only loads the MCP server when working in Android projects
- Avoids consuming context in unrelated projects
- Can be checked into version control for team sharing

**Alternative: Global configuration**

Add to `~/.mcp.json` if you want the server available in all projects:

```json
{
  "mcpServers": {
    "android-device": {
      "command": "android-device-mcp"
    }
  }
}
```

**Note**: After modifying MCP configuration, restart Claude Code for changes to take effect.

## Quick Start

1. Connect an Android device via USB (or start an emulator)
2. Enable USB debugging on the device
3. Verify connection: `adb devices`
4. Start using the MCP tools in Claude Code

```
# Check device connection
device_info

# Find an element
find_element(text="Login")

# Tap on it
tap_element(text="Login")
```

## Context Efficiency Best Practices

MCP tool responses consume context tokens. These best practices help minimize token usage:

### Hierarchy Tools (Most Important)

```python
# BAD: Full hierarchy can be 10,000+ tokens
get_layout_hierarchy()

# GOOD: Filter to interactive elements only (~80% reduction)
get_layout_hierarchy(clickable_only=True)

# BETTER: Limit depth and exclude system UI
get_layout_hierarchy(clickable_only=True, max_depth=5, include_system_ui=False)

# BEST: Use bounds for lightest response (~90% reduction)
get_layout_bounds(clickable_only=True, limit=20)
```

### Tool Selection Guide

| Need | Tool | Token Impact |
|------|------|--------------|
| Quick element check | `find_element(text="...")` | ~50 tokens |
| Interactive elements list | `get_layout_bounds(clickable_only=True)` | ~500 tokens |
| Full UI structure | `get_layout_hierarchy(clickable_only=True)` | ~2,000 tokens |
| Debugging layout | `get_layout_hierarchy()` | ~10,000+ tokens |

### Screenshots (UI Verification)

For UI verification work, use these context-efficient approaches:

```python
# BAD: Full screenshot returns large base64 (~1MB+ for high-res screens)
screenshot()

# GOOD: Resize to manageable size
screenshot(max_width=800)

# BETTER: Save to file, then use Claude Code's Read tool to view
screenshot(save_to_file="./screenshots/feed_screen.png")

# BEST: Capture specific element only
screenshot(element_selector="launch_card", max_width=600)
```

**Key parameters:**
- `save_to_file`: Saves screenshot to disk instead of returning base64. Claude Code can read the image file directly, which is much more context-efficient.
- `max_width`: Resizes screenshot while maintaining aspect ratio. Use 800-1024 for readable images.
- `element_selector`: Captures just a specific element by text, resource_id, or content_desc.
- Screenshots >500KB are automatically saved to a temp file with the path returned.

**UI Review Workflow:**
1. `screenshot(save_to_file="./screen.png", max_width=800)`
2. Use Claude Code's Read tool on `./screen.png` to view the image
3. Use `get_layout_bounds(clickable_only=True)` to understand interactive elements

## Tools Overview

### Visual Tools
| Tool | Description |
|------|-------------|
| `screenshot` | Capture screen or element (supports `save_to_file`, `max_width`, `element_selector`) |
| `get_screen_size` | Get device resolution |
| `get_layout_hierarchy` | Full UI tree as XML (supports `clickable_only`, `max_depth`, `include_system_ui`) |
| `get_layout_bounds` | Element bounds only - **most efficient** (supports `clickable_only`, `limit`) |
| `find_element` | Find single element by selector |
| `find_elements` | Find all matching elements |
| `screen_record_start` | Start video recording |
| `screen_record_stop` | Stop and return video |

### Interaction Tools
| Tool | Description |
|------|-------------|
| `tap` | Tap at coordinates |
| `tap_element` | Tap element by selector |
| `double_tap` | Double tap |
| `long_press` | Long press |
| `swipe` | Swipe gesture |
| `scroll` | Scroll in direction |
| `pinch` | Pinch zoom |
| `drag` | Drag gesture |
| `type_text` | Type text |
| `press_key` | Hardware key press |

### Observation Tools
| Tool | Description |
|------|-------------|
| `device_info` | Device model, API level, etc. |
| `shell` | Execute shell command |
| `logcat` | Get device logs |
| `get_current_activity` | Current foreground activity |
| `get_current_package` | Current foreground package |
| `wait_for_element` | Wait for element to appear |
| `wait_for_idle` | Wait for UI to stabilize |

### App Management
| Tool | Description |
|------|-------------|
| `install_apk` | Install APK file |
| `uninstall_app` | Uninstall app |
| `launch_app` | Launch app |
| `stop_app` | Force stop app |
| `clear_app_data` | Clear app data |
| `list_packages` | List installed packages |
| `get_app_info` | Get app details |

### Learning Tools
| Tool | Description |
|------|-------------|
| `pattern_save` | Save learned pattern |
| `pattern_get` | Retrieve pattern |
| `pattern_list` | List patterns for app |
| `pattern_delete` | Delete pattern |
| `interaction_log` | Log interaction result |
| `get_reliability_stats` | Get success rates |

## Configuration

Configure via environment variables:

```bash
# Screenshot settings
export ANDROID_MCP_SCREENSHOT_FORMAT=png  # png, jpeg, webp
export ANDROID_MCP_SCREENSHOT_QUALITY=80  # 1-100

# Target specific device
export ANDROID_MCP_DEFAULT_DEVICE=emulator-5554

# Learning settings
export ANDROID_MCP_LEARNING_ENABLED=true
export ANDROID_MCP_DB_PATH=/path/to/learning.db

# Security
export ANDROID_MCP_ALLOW_SHELL=true
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code                               │
│                                                                   │
│  ┌──────────────────┐    ┌────────────────────────────────────┐ │
│  │   SKILL.md       │    │   android-device MCP Server        │ │
│  │                  │    │                                    │ │
│  │ • Best practices │───▶│ • 30+ device interaction tools    │ │
│  │ • Workflows      │    │ • Built-in SQLite learning store  │ │
│  │ • Troubleshooting│    │ • ADB + uiautomator2              │ │
│  └──────────────────┘    └─────────────┬──────────────────────┘ │
└────────────────────────────────────────┼────────────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    ▼                    │
                    │          Android Device(s)              │
                    │     (Physical or Emulator via ADB)      │
                    └─────────────────────────────────────────┘
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
ruff check src/

# Type check
mypy src/
```

## License

MIT
