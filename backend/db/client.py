"""
Herofy Database Client
asyncpg connection pool with helpers matching Express patterns
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import UUID

import asyncpg

from core.errors import DatabaseError, DatabaseNotConnectedError
from core.logging import get_logger

logger = get_logger("DatabaseClient")

# Global client instance
_client: "DatabaseClient | None" = None


class DatabaseClient:
    """
    Async PostgreSQL client with connection pooling.
    Mirrors Express patterns from shared/src/db.ts
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create connection pool."""
        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=20,
                command_timeout=60,
                # JSON serialization
                init=self._init_connection,
            )
            logger.info("database_connected", pool_size=20)
        except Exception as e:
            logger.error("database_connection_failed", error=str(e))
            raise DatabaseError(f"Failed to connect to database: {e}")

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize connection with JSON type codecs."""
        await conn.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )
        await conn.set_type_codec(
            "json",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("database_disconnected")

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the connection pool, raising if not connected."""
        if not self._pool:
            raise DatabaseNotConnectedError()
        return self._pool

    # =========================================================================
    # Query Helpers (mirrors Express db.ts)
    # =========================================================================

    async def query(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a parameterized SQL query.
        Returns list of rows as dicts.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *(params or []))
            return [dict(row) for row in rows]

    async def query_one(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Execute query and return first row or None.
        Mirrors Express queryOne.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *(params or []))
            return dict(row) if row else None

    async def query_all(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute query and return all rows.
        Alias for query() for consistency with Express.
        """
        return await self.query(sql, params)

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Insert row with RETURNING *.
        Mirrors Express insert().
        """
        # Filter out None values and convert types
        clean_data = self._prepare_data(data)

        keys = list(clean_data.keys())
        values = [clean_data[k] for k in keys]
        placeholders = [f"${i+1}" for i in range(len(keys))]

        columns = ", ".join(keys)
        placeholders_str = ", ".join(placeholders)

        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders_str}) RETURNING *"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *values)
            if not row:
                raise DatabaseError(f"Insert into {table} returned no row")
            return dict(row)

    async def update(
        self,
        table: str,
        id: str | UUID,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Update row by id with RETURNING *.
        Mirrors Express update().
        """
        if not data:
            return await self.query_one(
                f"SELECT * FROM {table} WHERE id = $1", [str(id)]
            )

        clean_data = self._prepare_data(data)
        keys = list(clean_data.keys())
        values = [clean_data[k] for k in keys]

        set_clause = ", ".join([f"{k} = ${i+1}" for i, k in enumerate(keys)])
        sql = f"UPDATE {table} SET {set_clause} WHERE id = ${len(keys)+1} RETURNING *"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *values, str(id))
            return dict(row) if row else None

    async def delete(
        self,
        table: str,
        id: str | UUID,
    ) -> bool:
        """Delete row by id. Returns True if deleted."""
        sql = f"DELETE FROM {table} WHERE id = $1"
        async with self.pool.acquire() as conn:
            result = await conn.execute(sql, str(id))
            return result == "DELETE 1"

    async def execute(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> str:
        """
        Execute a SQL statement (INSERT, UPDATE, DELETE, etc.).
        Returns the command status string (e.g., "INSERT 0 1").
        """
        async with self.pool.acquire() as conn:
            return await conn.execute(sql, *(params or []))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Transaction context manager.

        Usage:
            async with db.transaction() as conn:
                await conn.execute("INSERT ...")
                await conn.execute("UPDATE ...")
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    # =========================================================================
    # Helpers
    # =========================================================================

    def _prepare_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Prepare data for SQL insertion - convert types and handle special values."""
        result = {}
        for key, value in data.items():
            if value is None:
                continue
            # Convert UUIDs to strings
            if isinstance(value, UUID):
                result[key] = str(value)
            # Convert datetime to ISO format for text columns
            elif isinstance(value, datetime) and key.endswith("_at"):
                result[key] = value
            # Pass lists/dicts directly - asyncpg handles JSONB encoding via codecs
            else:
                result[key] = value
        return result


# =========================================================================
# Global Client Access
# =========================================================================


async def init_db_client(database_url: str) -> DatabaseClient:
    """Initialize the global database client."""
    global _client
    _client = DatabaseClient(database_url)
    await _client.connect()
    return _client


async def close_db_client() -> None:
    """Close the global database client."""
    global _client
    if _client:
        await _client.disconnect()
        _client = None


def get_db_client() -> DatabaseClient:
    """Get the global database client instance."""
    if not _client:
        raise DatabaseNotConnectedError("Database client not initialized")
    return _client
