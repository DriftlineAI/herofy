"""
Global Playbook Catalog Seed
One-time initialization of milestone blocks and playbook templates.

Run with: python seed_catalog.py

This seeds the GLOBAL catalog that all workspaces can access.
It does NOT create per-workspace data.
"""

import asyncio
import uuid
from db.dataconnect_client import get_dataconnect_client, init_dataconnect_client

# =============================================================================
# MILESTONE BLOCKS
# Reusable components with institutional knowledge
# =============================================================================

MILESTONE_BLOCKS = [
    # KICKOFF
    {
        "id": str(uuid.uuid4()),
        "slug": "kickoff-call",
        "name": "Kickoff Call",
        "description": "Align on goals, timeline, success criteria, and introduce key stakeholders",
        "ownerSide": "us",
        "typicalDays": 3,
        "minDays": 1,
        "maxDays": 7,
        "category": "kickoff",
        "prerequisites": "[]",
        "tags": '["required", "all-plans"]',
        "sortOrder": 1,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "goals-alignment",
        "name": "Goals Alignment",
        "description": "Document and validate customer success criteria and business outcomes",
        "ownerSide": "joint",
        "typicalDays": 2,
        "minDays": 1,
        "maxDays": 5,
        "category": "kickoff",
        "prerequisites": '["kickoff-call"]',
        "tags": '["required", "all-plans"]',
        "sortOrder": 2,
    },
    # SETUP
    {
        "id": str(uuid.uuid4()),
        "slug": "account-setup",
        "name": "Account Setup",
        "description": "Create workspace, configure basic settings, invite initial users",
        "ownerSide": "joint",
        "typicalDays": 2,
        "minDays": 1,
        "maxDays": 5,
        "category": "setup",
        "prerequisites": '["kickoff-call"]',
        "tags": '["required", "all-plans"]',
        "sortOrder": 10,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "user-provisioning",
        "name": "User Provisioning",
        "description": "Set up user accounts, roles, and permissions for the team",
        "ownerSide": "customer",
        "typicalDays": 3,
        "minDays": 1,
        "maxDays": 7,
        "category": "setup",
        "prerequisites": '["account-setup"]',
        "tags": '["standard"]',
        "sortOrder": 11,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "sso-setup",
        "name": "SSO Configuration",
        "description": "Configure Single Sign-On integration (SAML, OAuth, etc.)",
        "ownerSide": "customer",
        "typicalDays": 5,
        "minDays": 3,
        "maxDays": 14,
        "category": "setup",
        "prerequisites": '["account-setup"]',
        "tags": '["enterprise", "security", "technical"]',
        "sortOrder": 12,
    },
    # INTEGRATION
    {
        "id": str(uuid.uuid4()),
        "slug": "crm-integration",
        "name": "CRM Integration",
        "description": "Connect and configure CRM system (Salesforce, HubSpot, etc.)",
        "ownerSide": "joint",
        "typicalDays": 5,
        "minDays": 2,
        "maxDays": 14,
        "category": "integration",
        "prerequisites": '["account-setup"]',
        "tags": '["technical", "integration"]',
        "sortOrder": 20,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "api-setup",
        "name": "API Setup",
        "description": "Configure API access, generate keys, set up authentication",
        "ownerSide": "joint",
        "typicalDays": 3,
        "minDays": 1,
        "maxDays": 7,
        "category": "integration",
        "prerequisites": '["account-setup"]',
        "tags": '["technical", "integration"]',
        "sortOrder": 21,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "data-warehouse-connect",
        "name": "Data Warehouse Connection",
        "description": "Connect to data warehouse (Snowflake, BigQuery, Redshift)",
        "ownerSide": "customer",
        "typicalDays": 5,
        "minDays": 2,
        "maxDays": 14,
        "category": "integration",
        "prerequisites": '["account-setup"]',
        "tags": '["technical", "enterprise", "integration"]',
        "sortOrder": 22,
    },
    # DATA
    {
        "id": str(uuid.uuid4()),
        "slug": "data-migration",
        "name": "Data Migration",
        "description": "Import historical data, validate accuracy, resolve conflicts",
        "ownerSide": "joint",
        "typicalDays": 7,
        "minDays": 3,
        "maxDays": 21,
        "category": "data",
        "prerequisites": '["account-setup"]',
        "tags": '["technical", "data"]',
        "sortOrder": 30,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "data-validation",
        "name": "Data Validation",
        "description": "Verify imported data accuracy, fix issues, confirm with customer",
        "ownerSide": "joint",
        "typicalDays": 3,
        "minDays": 1,
        "maxDays": 7,
        "category": "data",
        "prerequisites": '["data-migration"]',
        "tags": '["data"]',
        "sortOrder": 31,
    },
    # TRAINING
    {
        "id": str(uuid.uuid4()),
        "slug": "admin-training",
        "name": "Admin Training",
        "description": "Train administrators on configuration, user management, and settings",
        "ownerSide": "us",
        "typicalDays": 2,
        "minDays": 1,
        "maxDays": 5,
        "category": "training",
        "prerequisites": '["account-setup"]',
        "tags": '["training"]',
        "sortOrder": 40,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "end-user-training",
        "name": "End User Training",
        "description": "Train end users on daily workflows and core features",
        "ownerSide": "us",
        "typicalDays": 3,
        "minDays": 1,
        "maxDays": 7,
        "category": "training",
        "prerequisites": '["admin-training"]',
        "tags": '["training"]',
        "sortOrder": 41,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "self-serve-guides",
        "name": "Self-Serve Resources",
        "description": "Share documentation, videos, and help resources for ongoing learning",
        "ownerSide": "us",
        "typicalDays": 1,
        "minDays": 1,
        "maxDays": 3,
        "category": "training",
        "prerequisites": "[]",
        "tags": '["training", "self-serve"]',
        "sortOrder": 42,
    },
    # VALIDATION
    {
        "id": str(uuid.uuid4()),
        "slug": "pilot-program",
        "name": "Pilot Program",
        "description": "Run limited pilot with select users before full rollout",
        "ownerSide": "joint",
        "typicalDays": 14,
        "minDays": 7,
        "maxDays": 30,
        "category": "validation",
        "prerequisites": '["end-user-training"]',
        "tags": '["enterprise", "validation"]',
        "sortOrder": 50,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "uat-testing",
        "name": "User Acceptance Testing",
        "description": "Customer validates workflows match requirements before go-live",
        "ownerSide": "customer",
        "typicalDays": 5,
        "minDays": 2,
        "maxDays": 14,
        "category": "validation",
        "prerequisites": '["end-user-training"]',
        "tags": '["validation"]',
        "sortOrder": 51,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "success-criteria-check",
        "name": "Success Criteria Check",
        "description": "Verify all defined success criteria are achievable with current setup",
        "ownerSide": "joint",
        "typicalDays": 2,
        "minDays": 1,
        "maxDays": 5,
        "category": "validation",
        "prerequisites": '["goals-alignment"]',
        "tags": '["validation"]',
        "sortOrder": 52,
    },
    # LAUNCH
    {
        "id": str(uuid.uuid4()),
        "slug": "go-live",
        "name": "Go-Live",
        "description": "Launch to production, monitor closely, provide real-time support",
        "ownerSide": "joint",
        "typicalDays": 3,
        "minDays": 1,
        "maxDays": 7,
        "category": "launch",
        "prerequisites": "[]",
        "tags": '["required", "all-plans"]',
        "sortOrder": 60,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "go-live-support",
        "name": "Go-Live Support",
        "description": "Dedicated support during first week of production use",
        "ownerSide": "us",
        "typicalDays": 5,
        "minDays": 3,
        "maxDays": 14,
        "category": "launch",
        "prerequisites": '["go-live"]',
        "tags": '["support"]',
        "sortOrder": 61,
    },
    # REVIEW
    {
        "id": str(uuid.uuid4()),
        "slug": "30-day-review",
        "name": "30-Day Review",
        "description": "Review adoption metrics, address issues, plan next phase",
        "ownerSide": "us",
        "typicalDays": 1,
        "minDays": 1,
        "maxDays": 3,
        "category": "review",
        "prerequisites": '["go-live"]',
        "tags": '["review"]',
        "sortOrder": 70,
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "value-realization",
        "name": "Value Realization Check",
        "description": "Measure achieved outcomes against initial success criteria",
        "ownerSide": "joint",
        "typicalDays": 2,
        "minDays": 1,
        "maxDays": 5,
        "category": "review",
        "prerequisites": '["30-day-review"]',
        "tags": '["review", "success"]',
        "sortOrder": 71,
    },
]

# =============================================================================
# PLAYBOOK TEMPLATES
# Curated combinations of blocks for common scenarios
# =============================================================================

PLAYBOOK_TEMPLATES = [
    {
        "id": str(uuid.uuid4()),
        "slug": "quick-start",
        "name": "Quick Start",
        "description": "Fast onboarding for simple setups with minimal integration. Ideal for self-serve or small teams getting started quickly.",
        "complexity": "simple",
        "estimatedDays": 14,
        "fitCriteria": '{"maxDays": 21, "noIntegrations": true, "selfServe": true}',
        "sortOrder": 1,
        "blocks": [
            "kickoff-call",
            "goals-alignment",
            "account-setup",
            "self-serve-guides",
            "go-live",
            "30-day-review",
        ],
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "standard-saas",
        "name": "Standard SaaS",
        "description": "Typical B2B onboarding with one integration and structured training. Most common pattern for SMB customers.",
        "complexity": "standard",
        "estimatedDays": 45,
        "fitCriteria": '{"minDays": 21, "maxDays": 60, "hasIntegration": true}',
        "sortOrder": 2,
        "blocks": [
            "kickoff-call",
            "goals-alignment",
            "account-setup",
            "user-provisioning",
            "crm-integration",
            "admin-training",
            "end-user-training",
            "uat-testing",
            "go-live",
            "go-live-support",
            "30-day-review",
        ],
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "integration-heavy",
        "name": "Integration Heavy",
        "description": "Multiple integrations and data migration. For customers connecting several systems or migrating significant data.",
        "complexity": "standard",
        "estimatedDays": 60,
        "fitCriteria": '{"multipleIntegrations": true, "hasDataMigration": true}',
        "sortOrder": 3,
        "blocks": [
            "kickoff-call",
            "goals-alignment",
            "account-setup",
            "user-provisioning",
            "crm-integration",
            "api-setup",
            "data-migration",
            "data-validation",
            "admin-training",
            "end-user-training",
            "uat-testing",
            "go-live",
            "go-live-support",
            "30-day-review",
            "value-realization",
        ],
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "enterprise",
        "name": "Enterprise",
        "description": "Full enterprise onboarding with SSO, compliance, and pilot program. For larger organizations with security requirements.",
        "complexity": "complex",
        "estimatedDays": 90,
        "fitCriteria": '{"hasSSO": true, "enterprise": true, "minDays": 60}',
        "sortOrder": 4,
        "blocks": [
            "kickoff-call",
            "goals-alignment",
            "account-setup",
            "sso-setup",
            "user-provisioning",
            "crm-integration",
            "api-setup",
            "data-warehouse-connect",
            "data-migration",
            "data-validation",
            "admin-training",
            "end-user-training",
            "pilot-program",
            "success-criteria-check",
            "go-live",
            "go-live-support",
            "30-day-review",
            "value-realization",
        ],
    },
    {
        "id": str(uuid.uuid4()),
        "slug": "extended-enterprise",
        "name": "Extended Enterprise",
        "description": "Comprehensive enterprise with change management. For multi-department rollouts requiring extensive validation.",
        "complexity": "complex",
        "estimatedDays": 120,
        "fitCriteria": '{"multiDepartment": true, "changeManagement": true, "minDays": 90}',
        "sortOrder": 5,
        "blocks": [
            "kickoff-call",
            "goals-alignment",
            "account-setup",
            "sso-setup",
            "user-provisioning",
            "crm-integration",
            "api-setup",
            "data-warehouse-connect",
            "data-migration",
            "data-validation",
            "admin-training",
            "end-user-training",
            "pilot-program",
            "uat-testing",
            "success-criteria-check",
            "go-live",
            "go-live-support",
            "30-day-review",
            "value-realization",
        ],
    },
]


async def seed_catalog():
    """Seed the global playbook catalog."""
    dc = get_dataconnect_client()

    print("Seeding milestone blocks...")
    block_id_by_slug = {}

    for block in MILESTONE_BLOCKS:
        try:
            await dc.execute_mutation("CreateMilestoneBlock", block)
            block_id_by_slug[block["slug"]] = block["id"]
            print(f"  Created block: {block['slug']}")
        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  Block already exists: {block['slug']}")
                # Fetch existing block ID
                result = await dc.execute_query(
                    "GetMilestoneBlocks",
                    {},
                )
                for b in result.get("milestoneBlocks", []):
                    block_id_by_slug[b["slug"]] = b["id"]
            else:
                print(f"  Error creating block {block['slug']}: {e}")

    print("\nSeeding playbook templates...")

    for template in PLAYBOOK_TEMPLATES:
        block_slugs = template.pop("blocks")

        try:
            await dc.execute_mutation("CreatePlaybookTemplate", template)
            print(f"  Created template: {template['slug']}")

            # Link blocks to template
            for sort_order, slug in enumerate(block_slugs):
                block_id = block_id_by_slug.get(slug)
                if block_id:
                    try:
                        await dc.execute_mutation(
                            "CreatePlaybookTemplateBlock",
                            {
                                "templateId": template["id"],
                                "blockId": block_id,
                                "sortOrder": sort_order,
                                "isRequired": slug in ["kickoff-call", "go-live"],
                            },
                        )
                    except Exception as e:
                        if "unique" not in str(e).lower() and "duplicate" not in str(e).lower():
                            print(f"    Error linking {slug}: {e}")
                else:
                    print(f"    Warning: Block not found: {slug}")

        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  Template already exists: {template['slug']}")
            else:
                print(f"  Error creating template {template['slug']}: {e}")

    print("\nCatalog seeding complete!")
    print(f"  Blocks: {len(MILESTONE_BLOCKS)}")
    print(f"  Templates: {len(PLAYBOOK_TEMPLATES)}")


async def check_catalog():
    """Check if catalog is already seeded."""
    dc = get_dataconnect_client()

    try:
        result = await dc.execute_query("GetMilestoneBlocks", {})
        blocks = result.get("milestoneBlocks", [])

        result = await dc.execute_query("GetPlaybookTemplates", {})
        templates = result.get("playbookTemplates", [])

        return len(blocks) > 0 and len(templates) > 0
    except Exception:
        return False


async def main():
    """Main entry point."""
    import sys

    # Initialize DataConnect client
    print("Initializing DataConnect client...")
    await init_dataconnect_client()

    if "--check" in sys.argv:
        seeded = await check_catalog()
        print(f"Catalog seeded: {seeded}")
        return

    if "--force" not in sys.argv:
        seeded = await check_catalog()
        if seeded:
            print("Catalog already seeded. Use --force to re-seed.")
            return

    await seed_catalog()


if __name__ == "__main__":
    asyncio.run(main())
