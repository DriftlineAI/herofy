"""
Herofy Backend Configuration
Pydantic Settings with environment variable loading
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://herofy:herofy_local@localhost:5432/herofy_dev"

    # Google AI
    gemini_api_key: str = ""
    google_cloud_project: str = ""

    # Server
    port: int = 8081
    log_level: str = "INFO"

    # Firebase
    firebase_project_id: str = "herofy-496505"
    firebase_credentials_path: str = ""  # Optional: path to service account JSON

    # Notion MCP
    notion_api_key: str = ""
    notion_database_id: str = ""

    # Notion OAuth (for autonomous agent)
    # Supports both NOTION_CLIENT_ID and NOTION_OAUTH_CLIENT_ID
    notion_client_id: str = ""
    notion_client_secret: str = ""
    notion_oauth_redirect_uri: str = "${APP_BASE_URL}/integrations/notion/callback"

    # Notion hosted MCP server (mcp.notion.com) — a SEPARATE OAuth 2.0 + PKCE + Dynamic Client
    # Registration flow from the REST integration above (the REST token is rejected by mcp.notion.com).
    # The client_id is a public client (no secret) and must be STABLE across a grant's lifetime so
    # refresh works. If left blank the provider does a one-time anonymous DCR and logs the client_id
    # to pin here (per redirect_uri, so dev and prod differ). See docs / provider for details.
    notion_mcp_client_id: str = ""

    # Slack Integration
    slack_signing_secret: str = ""
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_bot_token: str = ""        # Bot User OAuth Token (xoxb-...)
    slack_app_token: str = ""        # App-Level Token (xapp-...) for Socket Mode
    slack_mode: str = "webhook"      # "webhook" or "socket"

    # Google Pub/Sub (for Gmail/Calendar webhooks)
    google_pubsub_token: str = ""
    google_pubsub_topic: str = ""  # e.g., "projects/herofy-496505/topics/gmail-push"

    # Google OAuth (for Gmail)
    # Supports both GOOGLE_CLIENT_ID and GOOGLE_OAUTH_CLIENT_ID
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "${APP_BASE_URL}/integrations/gmail/callback"

    # Slack OAuth redirect (override only if you need a non-default path)
    slack_oauth_redirect_uri: str = ""

    # OAuth Token Encryption
    # Generate key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    oauth_encryption_key: str = ""

    # Body Encryption (for interactions.body_encrypted)
    # Generate key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    body_encryption_key: str = ""

    # Autonomous Agent Settings
    agent_poll_interval_minutes: int = 15
    agent_question_timeout_hours: int = 24
    agent_fallback_on_timeout: bool = True

    # Orchestrator (net-new queue-driven worker, side-by-side with handoff_auto)
    # Env: ORCHESTRATION_ENABLED. Mount-only flag — when False (default) the
    # orchestrator routes/queue/consumer are never registered and the backend
    # behaves exactly as today. When True the /demo-agent endpoint + queue worker
    # + plays go live ADDITIVELY; the working handoff_auto path is never touched.
    # Flip back to False + restart to revert with zero loss.
    orchestration_enabled: bool = False

    # Demo environment (per-visitor anonymous sandbox at demo.herofy.ai). Mount-only flag.
    # Env: DEMO_ENABLED. When False (default) the /demo provisioning router is never registered
    # AND anonymous Firebase tokens are rejected everywhere (see middleware/auth.py). When True the
    # demo router mounts and anonymous tokens are accepted ONLY on the demo endpoint allowlist.
    # @lru_cache'd → restart to change.
    demo_enabled: bool = False

    # Env: ORCHESTRATION_DRAIN_CONCURRENCY. How many AgentTasks a single drain
    # processes at once. The DB-level optimistic claim (ClaimAgentTask CAS) makes
    # concurrent claims collision-safe, so this is just a per-process throughput
    # knob — 20 queued tasks finish in ~1/N the wall-clock. 1 == legacy sequential
    # behavior. Stays within one process, so the in-memory session store is shared
    # (no DatabaseSessionService prerequisite). @lru_cache'd → restart to change.
    orchestration_drain_concurrency: int = 10

    # Metric Snapshots (time-series substrate — see docs/plans/SIGNAL_AGGREGATION.md)
    # Env: METRIC_SNAPSHOTS_ENABLED. Mount-only flag — when False (default) all
    # snapshot writes are no-ops, the sweep's daily heartbeat is skipped, and the
    # derived engagement-health detection never runs; the backend behaves exactly
    # as today. When True, append-on-change + heartbeat begin populating the
    # MetricSnapshot table ADDITIVELY. Flip back to False + restart to revert with
    # zero loss (existing rows are untouched; the table schema is always present).
    # Settings are @lru_cache'd, so toggling requires a backend restart.
    metric_snapshots_enabled: bool = False

    # Signal Classification Settings
    # "always_llm" = always use LLM for classification (demos, hackathons)
    # "threshold" = use regex first, LLM only if confidence < threshold
    signal_classification_mode: str = "threshold"
    signal_llm_confidence_threshold: float = 0.5  # Trigger LLM if regex confidence below this

    # Mock Data Settings (opt-in only, defaults to False)
    # Set to true to use mock signal sources when real integrations aren't configured
    # This is NEVER automatic - you must explicitly opt in
    use_mock_gmail: bool = False
    use_mock_slack: bool = False
    use_mock_notion: bool = False

    # Pinecone Vector Index (semantic memory recall — see orchestrator/memory/pinecone_ingest.py)
    # Env: PINECONE_API_KEY. When empty, vector_recall returns [] (no Pinecone client created).
    # Index must be created with dimension=768 (text-embedding-004 output) and metric=cosine.
    # Run `python scripts/seed_pinecone.py` after setting the key to pre-populate demo data.
    pinecone_api_key: str = ""
    pinecone_index_name: str = "herofy-memory"

    # Langfuse LLM Observability (optional)
    # Set LANGFUSE_SECRET_KEY to enable — all other Langfuse settings have safe defaults
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # OpenTelemetry (optional)
    # Set to OTLP endpoint like "localhost:4317" to enable tracing
    otel_exporter_endpoint: str = ""

    # Environment
    environment: str = "development"

    # CORS — comma-separated extra origins merged into allow_origins (optional).
    # Set CORS_ALLOWED_ORIGINS on the Cloud Run service with concrete URLs, e.g.
    # "https://herofy-496505.web.app,https://herofy-496505.firebaseapp.com".
    # NOTE: pydantic-settings does NOT expand ${...} placeholders — values are read literally.
    cors_allowed_origins: str = ""

    # Cloud Scheduler (for OIDC verification)
    cloud_scheduler_service_account: str = ""  # SA email for OIDC verification
    poll_service_url: str = ""  # Expected audience in OIDC token (e.g., "https://api.herofy.ai")

    # App Base URL (for generating invitation links)
    app_base_url: str = ""  # Set via APP_BASE_URL env var (required in production)

    # API Base URL (for webhook URLs, used by external services)
    api_base_url: str = ""  # Set via API_BASE_URL env var (required in production)

    # Internal API Key (for securing internal endpoints like scheduled jobs)
    internal_api_key: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    resend_from_email: str = "noreply@herofy.ai"
    resend_notify_email: str = "info@herofy.ai"

    # Firebase Data Connect
    # Emulator settings (for local development)
    dataconnect_emulator_host: str = "localhost"
    dataconnect_emulator_port: int = 9399
    # Production settings
    dataconnect_location: str = "us-central1"
    dataconnect_service: str = "herofy-prod-service"
    dataconnect_connector: str = "herofy"
    # Feature flag to enable DataConnect (set to True to use DataConnect instead of asyncpg)
    use_dataconnect: bool = True
    # Set to True to use emulator, False to use CloudSQL directly (requires ADC)
    use_dataconnect_emulator: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origins_extra(self) -> list[str]:
        """Parse CORS_ALLOWED_ORIGINS (comma-separated) into a list."""
        if not self.cors_allowed_origins.strip():
            return []
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    def validate_production_config(self) -> list[str]:
        """
        Validate that required environment variables are set for production.
        Returns a list of missing configuration items.
        """
        if not self.is_production:
            return []

        missing = []

        # Required URLs for production
        if not self.app_base_url:
            missing.append("APP_BASE_URL (required for invitation links and OAuth)")
        if not self.api_base_url:
            missing.append("API_BASE_URL (required for webhook URLs)")

        # OAuth redirect URIs (only required if OAuth is being used)
        if self.notion_client_id and not self.notion_oauth_redirect_uri:
            missing.append("NOTION_OAUTH_REDIRECT_URI (required when Notion OAuth is enabled)")
        if self.google_client_id and not self.google_oauth_redirect_uri:
            missing.append("GOOGLE_OAUTH_REDIRECT_URI (required when Google OAuth is enabled)")
        if self.slack_client_id and not self.slack_oauth_redirect_uri:
            missing.append("SLACK_OAUTH_REDIRECT_URI (required when Slack OAuth is enabled)")

        return missing

    def get_app_base_url_with_fallback(self) -> str:
        """Get app base URL with development fallback."""
        if self.app_base_url:
            return self.app_base_url
        if self.is_development:
            return "http://localhost:5173"
        raise ValueError("APP_BASE_URL must be set in production")

    def get_api_base_url_with_fallback(self) -> str:
        """Get API base URL with development fallback."""
        if self.api_base_url:
            return self.api_base_url
        if self.is_development:
            return "http://localhost:8081"
        raise ValueError("API_BASE_URL must be set in production")

    # NOTE: use_mock_notion is now an explicit field (see above), not inferred from notion_api_key.
    # This prevents silent fallback to mocks when testing real integrations.

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra env vars not defined in Settings


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Module-level instance for convenience
settings = get_settings()
