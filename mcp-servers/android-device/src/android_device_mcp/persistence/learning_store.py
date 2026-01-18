"""SQLite-based learning storage for patterns and interaction history."""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LearningStore:
    """SQLite storage for learned patterns and interaction history.

    This store persists learned UI patterns, interaction history, and device
    quirks across sessions, enabling the MCP server to improve over time.
    """

    SCHEMA = """
    -- Core pattern storage
    CREATE TABLE IF NOT EXISTS patterns (
        id INTEGER PRIMARY KEY,
        app_package TEXT NOT NULL,
        app_version TEXT,
        pattern_key TEXT NOT NULL,
        pattern_type TEXT NOT NULL,
        pattern_data TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        success_count INTEGER DEFAULT 0,
        failure_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(app_package, pattern_key)
    );

    -- Interaction history for reliability tracking
    CREATE TABLE IF NOT EXISTS interaction_log (
        id INTEGER PRIMARY KEY,
        app_package TEXT NOT NULL,
        action_type TEXT NOT NULL,
        target_selector TEXT,
        success INTEGER NOT NULL,
        error_message TEXT,
        latency_ms INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Device-specific quirks
    CREATE TABLE IF NOT EXISTS device_quirks (
        id INTEGER PRIMARY KEY,
        device_model TEXT NOT NULL,
        api_level INTEGER NOT NULL,
        quirk_type TEXT NOT NULL,
        quirk_data TEXT NOT NULL,
        UNIQUE(device_model, api_level, quirk_type)
    );

    -- Indexes for fast lookup
    CREATE INDEX IF NOT EXISTS idx_patterns_app ON patterns(app_package);
    CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
    CREATE INDEX IF NOT EXISTS idx_log_app ON interaction_log(app_package);
    CREATE INDEX IF NOT EXISTS idx_log_time ON interaction_log(created_at);
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize learning store.

        Args:
            db_path: Path to SQLite database. If None, operates as no-op.
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

        if db_path:
            self._init_db()

    def _init_db(self) -> None:
        """Initialize the database and create schema."""
        if not self.db_path:
            return

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()
        logger.info(f"Learning store initialized at {self.db_path}")

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        """Get database connection."""
        return self._conn

    async def save_pattern(
        self,
        app_package: str,
        pattern_key: str,
        pattern_type: str,
        pattern_data: dict,
        app_version: Optional[str] = None,
    ) -> dict:
        """Save or update a learned pattern.

        Args:
            app_package: App package name
            pattern_key: Unique key for pattern
            pattern_type: Type (element, flow, strategy, failure)
            pattern_data: Pattern data
            app_version: Optional app version

        Returns:
            Save confirmation
        """
        conn = self._get_conn()
        if not conn:
            return {"success": True, "message": "Learning disabled"}

        try:
            cursor = conn.cursor()

            # Check if exists
            cursor.execute(
                "SELECT id, success_count, failure_count FROM patterns "
                "WHERE app_package = ? AND pattern_key = ?",
                (app_package, pattern_key),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing
                cursor.execute(
                    """
                    UPDATE patterns SET
                        pattern_type = ?,
                        pattern_data = ?,
                        app_version = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE app_package = ? AND pattern_key = ?
                    """,
                    (
                        pattern_type,
                        json.dumps(pattern_data),
                        app_version,
                        app_package,
                        pattern_key,
                    ),
                )
                action = "updated"
            else:
                # Insert new
                cursor.execute(
                    """
                    INSERT INTO patterns
                    (app_package, pattern_key, pattern_type, pattern_data, app_version)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        app_package,
                        pattern_key,
                        pattern_type,
                        json.dumps(pattern_data),
                        app_version,
                    ),
                )
                action = "created"

            conn.commit()
            return {
                "success": True,
                "action": action,
                "pattern_key": pattern_key,
                "app_package": app_package,
            }

        except sqlite3.Error as e:
            logger.error(f"Failed to save pattern: {e}")
            return {"success": False, "error": str(e)}

    async def get_pattern(
        self, app_package: str, pattern_key: str
    ) -> Optional[dict]:
        """Retrieve a saved pattern.

        Args:
            app_package: App package name
            pattern_key: Pattern key

        Returns:
            Pattern data or None
        """
        conn = self._get_conn()
        if not conn:
            return None

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT pattern_type, pattern_data, confidence,
                       success_count, failure_count, created_at, updated_at
                FROM patterns
                WHERE app_package = ? AND pattern_key = ?
                """,
                (app_package, pattern_key),
            )
            row = cursor.fetchone()

            if row:
                return {
                    "pattern_key": pattern_key,
                    "app_package": app_package,
                    "pattern_type": row["pattern_type"],
                    "pattern_data": json.loads(row["pattern_data"]),
                    "confidence": row["confidence"],
                    "success_count": row["success_count"],
                    "failure_count": row["failure_count"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            return None

        except sqlite3.Error as e:
            logger.error(f"Failed to get pattern: {e}")
            return None

    async def list_patterns(
        self,
        app_package: str,
        pattern_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """List patterns for an app.

        Args:
            app_package: App package name
            pattern_type: Optional type filter
            limit: Maximum results

        Returns:
            List of pattern summaries
        """
        conn = self._get_conn()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            if pattern_type:
                cursor.execute(
                    """
                    SELECT pattern_key, pattern_type, confidence,
                           success_count, failure_count, updated_at
                    FROM patterns
                    WHERE app_package = ? AND pattern_type = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (app_package, pattern_type, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT pattern_key, pattern_type, confidence,
                           success_count, failure_count, updated_at
                    FROM patterns
                    WHERE app_package = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (app_package, limit),
                )

            return [
                {
                    "pattern_key": row["pattern_key"],
                    "pattern_type": row["pattern_type"],
                    "confidence": row["confidence"],
                    "success_count": row["success_count"],
                    "failure_count": row["failure_count"],
                    "updated_at": row["updated_at"],
                }
                for row in cursor.fetchall()
            ]

        except sqlite3.Error as e:
            logger.error(f"Failed to list patterns: {e}")
            return []

    async def delete_pattern(self, app_package: str, pattern_key: str) -> dict:
        """Delete a pattern.

        Args:
            app_package: App package name
            pattern_key: Pattern key

        Returns:
            Deletion result
        """
        conn = self._get_conn()
        if not conn:
            return {"success": True, "message": "Learning disabled"}

        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM patterns WHERE app_package = ? AND pattern_key = ?",
                (app_package, pattern_key),
            )
            conn.commit()

            if cursor.rowcount > 0:
                return {"success": True, "deleted": True}
            else:
                return {"success": True, "deleted": False, "message": "Pattern not found"}

        except sqlite3.Error as e:
            logger.error(f"Failed to delete pattern: {e}")
            return {"success": False, "error": str(e)}

    async def log_interaction(
        self,
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
            action_type: Type of action
            target_selector: Selector used
            success: Whether successful
            error_message: Error if failed
            latency_ms: Action latency

        Returns:
            Log confirmation
        """
        conn = self._get_conn()
        if not conn:
            return {"success": True, "message": "Learning disabled"}

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO interaction_log
                (app_package, action_type, target_selector, success, error_message, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    app_package,
                    action_type,
                    target_selector,
                    1 if success else 0,
                    error_message,
                    latency_ms,
                ),
            )

            # Update pattern stats if selector was used
            if target_selector:
                if success:
                    cursor.execute(
                        """
                        UPDATE patterns SET
                            success_count = success_count + 1,
                            confidence = MIN(1.0, confidence + 0.01)
                        WHERE app_package = ? AND pattern_key = ?
                        """,
                        (app_package, target_selector),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE patterns SET
                            failure_count = failure_count + 1,
                            confidence = MAX(0.1, confidence - 0.05)
                        WHERE app_package = ? AND pattern_key = ?
                        """,
                        (app_package, target_selector),
                    )

            conn.commit()
            return {"success": True, "logged": True}

        except sqlite3.Error as e:
            logger.error(f"Failed to log interaction: {e}")
            return {"success": False, "error": str(e)}

    async def get_reliability_stats(
        self, app_package: str, days: int = 30
    ) -> dict:
        """Get reliability statistics for an app.

        Args:
            app_package: App package name
            days: Number of days to analyze

        Returns:
            Success rates by action type
        """
        conn = self._get_conn()
        if not conn:
            return {"enabled": False}

        try:
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            cursor.execute(
                """
                SELECT action_type,
                       COUNT(*) as total,
                       SUM(success) as successes,
                       AVG(latency_ms) as avg_latency
                FROM interaction_log
                WHERE app_package = ? AND created_at > ?
                GROUP BY action_type
                """,
                (app_package, cutoff),
            )

            stats = {}
            for row in cursor.fetchall():
                total = row["total"]
                successes = row["successes"] or 0
                stats[row["action_type"]] = {
                    "total": total,
                    "successes": successes,
                    "success_rate": round(successes / total, 3) if total > 0 else 0,
                    "avg_latency_ms": round(row["avg_latency"]) if row["avg_latency"] else None,
                }

            return {
                "app_package": app_package,
                "period_days": days,
                "action_stats": stats,
            }

        except sqlite3.Error as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}

    async def decay_old_patterns(self, staleness_days: int = 30) -> int:
        """Decay confidence of old patterns.

        Args:
            staleness_days: Days after which to decay

        Returns:
            Number of patterns decayed
        """
        conn = self._get_conn()
        if not conn:
            return 0

        try:
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(days=staleness_days)).isoformat()

            cursor.execute(
                """
                UPDATE patterns SET
                    confidence = MAX(0.1, confidence * 0.9)
                WHERE updated_at < ?
                """,
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount

        except sqlite3.Error as e:
            logger.error(f"Failed to decay patterns: {e}")
            return 0

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
