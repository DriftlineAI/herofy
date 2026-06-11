# Herofy

**AI-powered Customer Success workspace for small B2B SaaS teams**

Herofy monitors your Gmail, Slack, Calendar, and Notion to surface what needs attention today, with AI agents that take autonomous action while keeping humans in the loop.

## Quick Start

### Prerequisites
- Node.js 18+
- Docker (for PostgreSQL)
- PostgreSQL client (`psql`)

### Setup

```bash
# 1. Install dependencies
npm install

# 2. Start the database
npm run db:up

# 3. Set up environment
cp agents/.env.example agents/.env
cp frontend/.env.example frontend/.env

# Edit agents/.env with your database URL:
# DATABASE_URL=postgres://herofy:herofy_local@localhost:5432/herofy_dev

# 4. Run migrations and seed demo data
npm run db:migrate
npm run db:seed

# 5. Start the development servers
npm run dev
```

The app will be available at:
- **Frontend**: http://localhost:3000
- **API Server**: http://localhost:8080

## Demo Walkthrough

### The Demo Scenario

The seed data includes a realistic scenario for demoing Herofy's HITL (Human-in-the-Loop) approval workflow:

1. **TechCorp Solutions** - A new deal just closed in Notion
   - $50K ARR, Mid-Market tier
   - 30-day timeline commitment (aggressive!)
   - Custom CRM integration required
   - HandoffChain agent has extracted the brief and generated a plan

### Demo Flow

**Step 1: Today Queue**
- Open the app at `/app`
- Notice "TechCorp onboarding plan ready for review" in the Today queue
- The ticker bar shows live stats: escalations, onboardings, ARR

**Step 2: Plan Approval (Dual-Pane UI)**
- Click "Review Plan" on the TechCorp need
- **Left pane**: Handoff Brief
  - Sales commitments (30-day timeline, Slack support, custom dashboard)
  - Technical context (REST API, Okta SSO, US-East data residency)
  - Reality check risks (timeline is tight!)
- **Right pane**: Generated Plan
  - 7 milestones, 35-day accelerated timeline
  - Each milestone has owner (us/customer/joint) and target day

**Step 3: HITL Actions**
Demo the 5 approval actions:
- **Edit Plan**: Adjust milestone timing or add steps
- **Edit Handoff**: Correct sales commitments, regenerate plan
- **Regenerate**: Get a new plan with the rejection feedback
- **Reject**: Provide a reason (feeds into next generation)
- **Approve**: Creates milestones, moves customer to onboarding

**Step 4: After Approval**
- Customer lifecycle changes from "handoff" to "onboarding"
- Milestones appear on the customer detail page
- Customer shows in the Onboarding view
- The plan approval need is auto-resolved

### Other Demo Scenarios

**At-Risk Customer (Globex)**
- Navigate to `/app/at-risk` or click "War Room" from Portfolio
- Globex Corporation: Champion departed, usage down 40%, CFO asking about downgrades
- Shows how Herofy surfaces urgent situations with AI reasoning

**Onboarding Progress (Acme Corp)**
- Navigate to `/app/onboarding`
- See Acme Corp blocked on API key generation
- Milestones timeline shows blocked status

**Portfolio View**
- Navigate to `/app/customers`
- Customers grouped by lifecycle: At Risk, Handoff, Onboarding, Renewing, Active
- Click any customer for full detail view with signals, stakeholders, goals

## Architecture

```
herofy/
├── frontend/          # React 19 + Vite + TailwindCSS 4
│   └── src/
│       ├── pages/     # Route pages
│       ├── components/# UI components
│       └── lib/       # API client & React Query hooks
├── agents/            # Express API server (TypeScript)
│   └── src/
│       └── routes/    # API endpoints
├── shared/            # Shared types & database utilities
├── db/
│   ├── migrations/    # PostgreSQL schema
│   └── seed.sql       # Demo data
└── backend/           # (Phase C) Python autonomous agents
```

## Key Features

### Today Queue
AI-prioritized list of what needs your attention. Each item includes:
- Customer context and ARR
- AI-generated headline and recommendation
- Quick actions: snooze, resolve
- Expandable "Why did this surface?" reasoning

### HITL Plan Approval
Dual-pane interface for reviewing AI-generated onboarding plans:
- Left: Editable handoff brief from sales
- Right: Editable milestones from AI
- 5 actions: Approve, Edit+Regenerate, Regenerate, Edit Plan, Reject
- Tracks human edits and regeneration count

### Handbook
Versioned documents that define how Herofy thinks:
- "Going Dark" criteria
- Renewal readiness framework
- Handoff quality standards
- AI references these when generating recommendations

### Live Ticker
Real-time dashboard stats in the footer:
- Escalation count
- Active onboardings
- Renewals in 30 days
- Pending approvals
- Portfolio ARR

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/workspaces/:id/today` | Today queue items |
| `GET /api/workspaces/:id/customers` | Customer list with signals |
| `GET /api/workspaces/:id/customers/:id` | Customer detail |
| `GET /api/plans/:id` | Plan with brief and customer |
| `POST /api/plans/:id/approve` | Approve plan (with optional edits) |
| `POST /api/plans/:id/reject` | Reject with reason |
| `POST /api/plans/:id/regenerate` | Mark as superseded, trigger regen |
| `GET /api/workspaces/:id/handoffs` | Handoff briefs list |
| `GET /api/workspaces/:id/handbook` | Handbook documents |
| `GET /api/workspaces/:id/dashboard` | Dashboard stats |

## Environment Variables

### agents/.env
```
DATABASE_URL=postgres://herofy:herofy_local@localhost:5432/herofy_dev
PORT=8080
NODE_ENV=development
```

### frontend/.env
```
VITE_API_URL=http://localhost:8080
```

## Tech Stack

- **Frontend**: React 19, React Router 7, Vite, TailwindCSS 4, Motion (Framer), TanStack Query
- **API Server**: Express, TypeScript, pg (PostgreSQL)
- **Database**: PostgreSQL 16
- **AI**: Gemini 2.0 Flash (for agent inference)

## License

Proprietary - Hackathon Demo
