"""Tests for the learning store."""

import pytest
import tempfile
from pathlib import Path

from android_device_mcp.persistence.learning_store import LearningStore


class TestLearningStore:
    """Tests for LearningStore."""

    @pytest.fixture
    def store(self):
        """Create a temporary learning store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = LearningStore(db_path)
            yield store
            store.close()

    @pytest.fixture
    def noop_store(self):
        """Create a no-op store (learning disabled)."""
        return LearningStore(None)

    @pytest.mark.asyncio
    async def test_save_and_get_pattern(self, store):
        """Test saving and retrieving a pattern."""
        result = await store.save_pattern(
            app_package="com.example.app",
            pattern_key="LoginButton",
            pattern_type="element",
            pattern_data={"selector": "com.app:id/login"},
        )

        assert result["success"]
        assert result["action"] == "created"

        pattern = await store.get_pattern("com.example.app", "LoginButton")

        assert pattern is not None
        assert pattern["pattern_type"] == "element"
        assert pattern["pattern_data"]["selector"] == "com.app:id/login"

    @pytest.mark.asyncio
    async def test_update_existing_pattern(self, store):
        """Test updating an existing pattern."""
        # Save initial
        await store.save_pattern(
            app_package="com.example.app",
            pattern_key="Button",
            pattern_type="element",
            pattern_data={"version": 1},
        )

        # Update
        result = await store.save_pattern(
            app_package="com.example.app",
            pattern_key="Button",
            pattern_type="element",
            pattern_data={"version": 2},
        )

        assert result["success"]
        assert result["action"] == "updated"

        pattern = await store.get_pattern("com.example.app", "Button")
        assert pattern["pattern_data"]["version"] == 2

    @pytest.mark.asyncio
    async def test_list_patterns(self, store):
        """Test listing patterns."""
        await store.save_pattern(
            app_package="com.example.app",
            pattern_key="Pattern1",
            pattern_type="element",
            pattern_data={},
        )
        await store.save_pattern(
            app_package="com.example.app",
            pattern_key="Pattern2",
            pattern_type="flow",
            pattern_data={},
        )

        all_patterns = await store.list_patterns("com.example.app")
        assert len(all_patterns) == 2

        element_patterns = await store.list_patterns("com.example.app", "element")
        assert len(element_patterns) == 1
        assert element_patterns[0]["pattern_key"] == "Pattern1"

    @pytest.mark.asyncio
    async def test_delete_pattern(self, store):
        """Test deleting a pattern."""
        await store.save_pattern(
            app_package="com.example.app",
            pattern_key="ToDelete",
            pattern_type="element",
            pattern_data={},
        )

        result = await store.delete_pattern("com.example.app", "ToDelete")
        assert result["success"]
        assert result["deleted"]

        pattern = await store.get_pattern("com.example.app", "ToDelete")
        assert pattern is None

    @pytest.mark.asyncio
    async def test_log_interaction(self, store):
        """Test logging interactions."""
        result = await store.log_interaction(
            app_package="com.example.app",
            action_type="tap",
            target_selector="com.app:id/button",
            success=True,
            latency_ms=50,
        )

        assert result["success"]
        assert result["logged"]

    @pytest.mark.asyncio
    async def test_reliability_stats(self, store):
        """Test reliability statistics."""
        # Log some interactions
        await store.log_interaction(
            app_package="com.example.app",
            action_type="tap",
            success=True,
        )
        await store.log_interaction(
            app_package="com.example.app",
            action_type="tap",
            success=True,
        )
        await store.log_interaction(
            app_package="com.example.app",
            action_type="tap",
            success=False,
        )

        stats = await store.get_reliability_stats("com.example.app")

        assert "action_stats" in stats
        assert "tap" in stats["action_stats"]
        assert stats["action_stats"]["tap"]["total"] == 3
        assert stats["action_stats"]["tap"]["successes"] == 2

    @pytest.mark.asyncio
    async def test_noop_store_operations(self, noop_store):
        """Test that noop store handles all operations gracefully."""
        # All operations should succeed without error
        result = await noop_store.save_pattern(
            app_package="com.example.app",
            pattern_key="Test",
            pattern_type="element",
            pattern_data={},
        )
        assert result["success"]

        pattern = await noop_store.get_pattern("com.example.app", "Test")
        assert pattern is None

        patterns = await noop_store.list_patterns("com.example.app")
        assert patterns == []

        stats = await noop_store.get_reliability_stats("com.example.app")
        assert not stats.get("enabled", True)
