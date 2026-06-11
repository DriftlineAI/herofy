"""
Pytest Configuration and Fixtures
Shared test fixtures for the Herofy backend
"""

import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Set test environment before importing app
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://herofy:herofy_local@localhost:5432/herofy_test",
)
os.environ["GEMINI_API_KEY"] = "test-api-key"

from main import app
from db.client import init_db_client, close_db_client, get_db_client


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_client():
    """
    Database client fixture.
    Creates a connection for each test and rolls back after.
    """
    await init_db_client(os.environ["DATABASE_URL"])
    client = get_db_client()
    yield client
    await close_db_client()


@pytest_asyncio.fixture(scope="function")
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client for testing FastAPI endpoints.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def workspace_id() -> str:
    """Test workspace ID from seed data."""
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def notion_deal_id() -> str:
    """Test Notion deal ID."""
    return "notion-deal-techcorp-001"


@pytest.fixture
def mock_deal_data() -> dict:
    """Mock deal data matching Notion tool output."""
    return {
        "company_name": "TestCorp",
        "arr_cents": 5000000,
        "sales_commitments": [
            {"item": "30-day implementation", "details": "Aggressive timeline"},
            {"item": "Dedicated support", "details": "Slack channel promised"},
        ],
        "technical_context": [
            {"item": "REST API integration", "details": "Custom CRM"},
            {"item": "SSO via Okta", "details": "Required"},
        ],
        "stakeholders": [
            {"name": "Jane Doe", "email": "jane@test.com", "role": "CEO"},
            {"name": "John Smith", "email": "john@test.com", "role": "CTO"},
        ],
        "timeline": "30 days",
        "notes": "High priority deal",
    }


@pytest.fixture
def mock_playbook() -> dict:
    """Mock playbook data."""
    return {
        "id": "55555555-5555-5555-5555-555555555551",
        "name": "Standard SaaS Onboarding",
        "archetype": "Mid-Market",
        "fit_note": "Best for $50K-$200K ARR",
        "drawn_from_count": 12,
    }


@pytest.fixture
def mock_milestones() -> list:
    """Mock playbook milestones."""
    return [
        {
            "id": "m1",
            "title": "Kickoff Call",
            "owner_side": "us",
            "duration_days": 7,
            "description": "Initial alignment",
            "sort_order": 1,
        },
        {
            "id": "m2",
            "title": "Technical Setup",
            "owner_side": "customer",
            "duration_days": 14,
            "description": "API configuration",
            "sort_order": 2,
        },
        {
            "id": "m3",
            "title": "Go-Live",
            "owner_side": "joint",
            "duration_days": 30,
            "description": "Production deployment",
            "sort_order": 3,
        },
    ]
