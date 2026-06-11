"""
Calendar Attendee Resolver

Resolves calendar attendees to customers and stakeholders.
Splits attendees into internal (our team) vs external (customer contacts).
"""

from typing import Any
from uuid import UUID

from core.logging import get_logger
from core.events import is_personal_email_domain

logger = get_logger("CalendarAttendeeResolver")


class CalendarAttendeeResolver:
    """
    Resolve calendar attendees to customers and stakeholders.

    Follows the unified customer resolution cascade from EventEmitterBase,
    but adapted for multi-attendee scenarios.
    """

    def __init__(self, workspace_id: str, workspace_domain: str):
        """
        Initialize resolver.

        Args:
            workspace_id: Workspace UUID
            workspace_domain: Workspace email domain for internal/external split
        """
        self.workspace_id = workspace_id
        self.workspace_domain = workspace_domain

    async def resolve_event_attendees(
        self,
        event: dict,
    ) -> dict[str, Any]:
        """
        Resolve all attendees in a calendar event.

        Args:
            event: Google Calendar event object

        Returns:
            {
                "customer_id": UUID | None,  # Primary customer for meeting
                "link_status": "linked" | "unlinked",
                "attendees_ours": [  # Internal team
                    {
                        "email": str,
                        "name": str,
                        "response_status": str,
                    }
                ],
                "attendees_theirs": [  # External contacts
                    {
                        "email": str,
                        "name": str,
                        "response_status": str,
                        "stakeholder_id": UUID | None,
                        "customer_id": UUID | None,
                        "role": str | None,
                    }
                ]
            }
        """
        attendees_ours = []
        attendees_theirs = []
        customer_candidates = {}  # customer_id -> count

        for att in event.get("attendees", []):
            email = att.get("email", "")
            name = att.get("displayName", email.split("@")[0] if "@" in email else email)
            response = att.get("responseStatus", "needsAction")

            if not email:
                continue

            domain = email.split("@")[-1].lower() if "@" in email else ""

            # Internal vs external
            if domain == self.workspace_domain.lower():
                attendees_ours.append({
                    "email": email,
                    "name": name,
                    "response_status": response,
                })
            else:
                # External attendee - resolve to customer
                customer_id, stakeholder_id, role = await self._resolve_external_attendee(
                    email, domain
                )

                attendees_theirs.append({
                    "email": email,
                    "name": name,
                    "response_status": response,
                    "stakeholder_id": str(stakeholder_id) if stakeholder_id else None,
                    "customer_id": str(customer_id) if customer_id else None,
                    "role": role,
                })

                # Track customer candidates
                if customer_id:
                    customer_candidates[customer_id] = customer_candidates.get(customer_id, 0) + 1

        # Determine primary customer
        primary_customer_id = None
        if customer_candidates:
            # Pick customer with most attendees
            primary_customer_id = max(customer_candidates, key=customer_candidates.get)

        link_status = "linked" if primary_customer_id else "unlinked"

        return {
            "customer_id": primary_customer_id,
            "link_status": link_status,
            "attendees_ours": attendees_ours,
            "attendees_theirs": attendees_theirs,
        }

    async def _resolve_external_attendee(
        self,
        email: str,
        domain: str,
    ) -> tuple[UUID | None, UUID | None, str | None]:
        """
        Resolve external attendee to customer and stakeholder.

        Args:
            email: Attendee email
            domain: Email domain

        Returns:
            (customer_id, stakeholder_id, role)
        """
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()

        # Step 1: Exact stakeholder match
        result = await dc.execute_query(
            "GetStakeholderByEmail",
            {
                "workspaceId": self.workspace_id,
                "email": email.lower(),
            },
        )

        stakeholders = result.get("stakeholders", [])
        if stakeholders:
            sh = stakeholders[0]
            customer = sh.get("customer", {})
            return (
                UUID(str(customer["id"])) if customer.get("id") else None,
                UUID(str(sh["id"])),
                sh.get("role"),
            )

        # Step 2: Domain match (skip personal domains)
        if not is_personal_email_domain(domain):
            result = await dc.execute_query(
                "GetCustomerByDomain",
                {
                    "workspaceId": self.workspace_id,
                    "domain": domain.lower(),
                },
            )

            customers = result.get("customers", [])
            if customers:
                customer_id = UUID(str(customers[0]["id"]))
                # Don't auto-create stakeholder - flag for review
                logger.debug(
                    "external_attendee_resolved_by_domain",
                    email=email,
                    domain=domain,
                    customer_id=str(customer_id),
                )
                return customer_id, None, None

        # Step 3: No match
        logger.debug(
            "external_attendee_not_resolved",
            email=email,
            domain=domain,
        )
        return None, None, None
