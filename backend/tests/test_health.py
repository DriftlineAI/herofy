"""
Health Endpoint Tests
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test basic health check returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness_check_without_db(client: AsyncClient):
    """Test readiness check when DB is not connected."""
    # Note: This will fail if DB is actually connected
    # In a real test, we'd mock the DB connection
    response = await client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
