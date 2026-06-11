-- Herofy Seed Data
-- Realistic demo data for the customer success workspace
-- Run with: docker exec -i herofy-db psql -U herofy -d herofy_dev < db/seed.sql

-- ============================================================================
-- WORKSPACE & USER
-- ============================================================================

INSERT INTO workspaces (id, name, slug) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Acme CS Team', 'acme-cs');

-- Placeholder user (replace with your Firebase UID after auth setup)
INSERT INTO users (id, email, display_name) VALUES
  ('22222222-2222-2222-2222-222222222221', 'dev@herofy.com', 'Demo User'),
  ('22222222-2222-2222-2222-222222222222', 'sarah@acme.com', 'Sarah Chen');

INSERT INTO workspace_members (workspace_id, user_id, role) VALUES
  ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222221', 'owner'),
  ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'csm');

-- ============================================================================
-- HANDBOOK DOCS (for AI versioning)
-- ============================================================================

INSERT INTO handbook_docs (id, workspace_id, slug, title, description, body, blast_radius) VALUES
  ('33333333-3333-3333-3333-333333333331', '11111111-1111-1111-1111-111111111111', 'going-dark',
   'How We Define Going Dark',
   'Criteria for identifying customers who have gone silent',
   E'# Going Dark Definition\n\nA customer is "going dark" when:\n\n1. No response to 2+ outreach attempts over 7 days\n2. Engagement score dropped >30% in the last 14 days\n3. Key stakeholders haven''t logged in for 10+ days\n4. Open commitments are overdue with no communication\n\n## Response Protocol\n\n1. Escalate to champion''s backup contact\n2. Try alternative channels (Slack if email is primary)\n3. Surface as priority need if no response in 48h',
   'medium'),

  ('33333333-3333-3333-3333-333333333332', '11111111-1111-1111-1111-111111111111', 'renewal-readiness',
   'How We Think About Renewal Readiness',
   'Framework for assessing renewal probability',
   E'# Renewal Readiness Framework\n\n## Ready (Green)\n- Champion actively advocating\n- Usage metrics trending up\n- No open escalations\n- Budget confirmed\n\n## Tracking (Yellow)\n- Some positive signals but gaps\n- Need more stakeholder coverage\n- Usage stable but not growing\n\n## At Risk (Red)\n- Champion departed or quiet\n- Usage declining\n- Open escalations or complaints\n- Budget discussions or downgrade inquiries',
   'high'),

  ('33333333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111', 'handoff-quality',
   'Sales to CS Handoff Quality Standards',
   'What makes a good handoff and how to identify risks early',
   E'# Handoff Quality Standards\n\n## Required Information\n- Primary stakeholders and roles\n- Technical requirements and constraints\n- Sales commitments (explicit and implied)\n- Success criteria from customer''s perspective\n- Timeline expectations\n\n## Red Flags to Surface\n- Unrealistic timelines promised\n- Technical requirements not validated\n- Missing executive sponsor\n- Vague success criteria\n- Discount or special terms not documented',
   'high');

-- Create initial versions for handbook docs
INSERT INTO handbook_versions (id, doc_id, body, edited_by_user_id, edited_at) VALUES
  ('44444444-4444-4444-4444-444444444441', '33333333-3333-3333-3333-333333333331', (SELECT body FROM handbook_docs WHERE id = '33333333-3333-3333-3333-333333333331'), '22222222-2222-2222-2222-222222222221', NOW()),
  ('44444444-4444-4444-4444-444444444442', '33333333-3333-3333-3333-333333333332', (SELECT body FROM handbook_docs WHERE id = '33333333-3333-3333-3333-333333333332'), '22222222-2222-2222-2222-222222222221', NOW()),
  ('44444444-4444-4444-4444-444444444443', '33333333-3333-3333-3333-333333333333', (SELECT body FROM handbook_docs WHERE id = '33333333-3333-3333-3333-333333333333'), '22222222-2222-2222-2222-222222222221', NOW());

-- ============================================================================
-- PLAYBOOKS
-- ============================================================================

INSERT INTO playbooks (id, workspace_id, name, archetype, fit_note, drawn_from_count) VALUES
  ('55555555-5555-5555-5555-555555555551', '11111111-1111-1111-1111-111111111111',
   'Standard SaaS Onboarding',
   'Mid-Market',
   'Best for $50K-$200K ARR accounts with dedicated technical resources',
   12),

  ('55555555-5555-5555-5555-555555555552', '11111111-1111-1111-1111-111111111111',
   'Enterprise Custom Implementation',
   'Enterprise',
   'For $200K+ ARR with complex integrations, security reviews, and multiple stakeholder groups',
   5);

INSERT INTO playbook_milestones (playbook_id, title, owner_side, duration_days, description, sort_order) VALUES
  -- Standard SaaS Onboarding milestones
  ('55555555-5555-5555-5555-555555555551', 'Kickoff Call', 'us', 7, 'Initial alignment on goals, timeline, and success criteria', 1),
  ('55555555-5555-5555-5555-555555555551', 'Technical Setup', 'customer', 14, 'API keys generated, environments configured, initial integration', 2),
  ('55555555-5555-5555-5555-555555555551', 'Data Migration', 'joint', 21, 'Historical data imported and validated', 3),
  ('55555555-5555-5555-5555-555555555551', 'User Training', 'us', 28, 'Admin and end-user training sessions completed', 4),
  ('55555555-5555-5555-5555-555555555551', 'UAT Sign-off', 'customer', 35, 'Customer validates functionality meets requirements', 5),
  ('55555555-5555-5555-5555-555555555551', 'Go-Live', 'joint', 42, 'Production deployment and cutover from legacy system', 6),

  -- Enterprise Custom Implementation milestones
  ('55555555-5555-5555-5555-555555555552', 'Executive Alignment', 'us', 7, 'C-level sponsor identified and aligned on vision', 1),
  ('55555555-5555-5555-5555-555555555552', 'Security Review', 'customer', 21, 'InfoSec review and approval completed', 2),
  ('55555555-5555-5555-5555-555555555552', 'Technical Discovery', 'joint', 28, 'Architecture review, integration mapping, requirements finalized', 3),
  ('55555555-5555-5555-5555-555555555552', 'Custom Development', 'us', 56, 'Custom integrations and configurations built', 4),
  ('55555555-5555-5555-5555-555555555552', 'Pilot Launch', 'joint', 70, 'Limited rollout to pilot group', 5);

-- ============================================================================
-- CUSTOMERS (Various lifecycle stages)
-- ============================================================================

INSERT INTO customers (id, workspace_id, name, slug, one_liner, tier, arr_cents, lifecycle, days_to_renewal, onboarding_day_current, onboarding_day_total, renewal_readiness, value_realization_text) VALUES
  -- ACTIVE customers
  ('66666666-6666-6666-6666-666666666661', '11111111-1111-1111-1111-111111111111',
   'Stripe', 'stripe',
   'Payment infrastructure, heavy API users',
   'Enterprise', 24000000, 'active', 180, NULL, NULL, 'ready',
   'Reduced payment reconciliation time by 60%'),

  ('66666666-6666-6666-6666-666666666662', '11111111-1111-1111-1111-111111111111',
   'Linear', 'linear',
   'Issue tracking for high-velocity teams',
   'Growth', 8500000, 'active', 220, NULL, NULL, 'tracking',
   'Engineering velocity metrics up 25%'),

  -- RENEWING customers
  ('66666666-6666-6666-6666-666666666663', '11111111-1111-1111-1111-111111111111',
   'Notion', 'notion',
   'Workspace for notes and collaboration',
   'Enterprise', 18000000, 'renewing', 45, NULL, NULL, 'tracking',
   NULL),

  ('66666666-6666-6666-6666-666666666664', '11111111-1111-1111-1111-111111111111',
   'Figma', 'figma',
   'Design collaboration platform',
   'Growth', 12000000, 'renewing', 28, NULL, NULL, 'ready',
   'Design handoff time cut in half'),

  -- AT_RISK customer (for demo scenario)
  ('66666666-6666-6666-6666-666666666665', '11111111-1111-1111-1111-111111111111',
   'Globex Corporation', 'globex',
   'Industrial automation, complex deployment',
   'Enterprise', 15000000, 'at_risk', 88, NULL, NULL, 'at_risk',
   NULL),

  -- ONBOARDING customers
  ('66666666-6666-6666-6666-666666666666', '11111111-1111-1111-1111-111111111111',
   'Acme Corp', 'acme-corp',
   'Manufacturing SaaS, API-first integration',
   'Mid-Market', 8500000, 'onboarding', NULL, 18, 45, NULL,
   NULL),

  ('66666666-6666-6666-6666-666666666667', '11111111-1111-1111-1111-111111111111',
   'Stark Industries', 'stark',
   'Defense tech, strict compliance requirements',
   'Enterprise', 25000000, 'onboarding', NULL, 5, 90, NULL,
   NULL),

  -- HANDOFF customer (ready for demo trigger)
  ('66666666-6666-6666-6666-666666666668', '11111111-1111-1111-1111-111111111111',
   'TechCorp Solutions', 'techcorp',
   'B2B SaaS platform, eager for quick launch',
   'Mid-Market', 5000000, 'handoff', NULL, 0, 42, NULL,
   NULL);

-- ============================================================================
-- STAKEHOLDERS
-- ============================================================================

INSERT INTO stakeholders (workspace_id, customer_id, name, email, role, status, sentiment_note) VALUES
  -- Stripe
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'Patrick Collison', 'patrick@stripe.com', 'CEO', 'active', 'Executive sponsor, very engaged'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'David Singleton', 'david@stripe.com', 'CTO', 'active', 'Technical champion'),

  -- Globex (at risk)
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'Hank Scorpio', 'hank@globex.com', 'VP Operations', 'active', 'Champion, but frustrated with delays'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'Frank Grimes', 'frank@globex.com', 'Technical Lead', 'departed', 'Left the company 2 weeks ago'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'Sarah Chen', 'sarah@globex.com', 'CFO', 'active', 'Asking about downgrades'),

  -- Acme Corp (onboarding)
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'Wile E. Coyote', 'wile@acme-corp.com', 'CTO', 'active', 'Technical decision maker'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'Road Runner', 'rr@acme-corp.com', 'Engineering Manager', 'active', 'Day-to-day contact'),

  -- TechCorp (handoff)
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666668', 'Alex Rivera', 'alex@techcorp.io', 'CEO', 'active', 'Executive sponsor'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666668', 'Jordan Park', 'jordan@techcorp.io', 'VP Engineering', 'active', 'Technical champion');

-- ============================================================================
-- GOALS
-- ============================================================================

INSERT INTO goals (workspace_id, customer_id, text, status, sort_order) VALUES
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'Achieve 99.99% uptime SLA compliance', 'active', 1),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'Reduce payment reconciliation time by 50%', 'achieved', 2),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'Complete Phase 2 integration by Q4', 'active', 1),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'Train 50 operators on new system', 'active', 2),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'Go live before end of quarter', 'active', 1);

-- ============================================================================
-- SIGNALS (Current state per customer)
-- ============================================================================

INSERT INTO signals (workspace_id, customer_id, kind, state, sentence, evidence_text, next_action, model, prompt_version, inputs_hash, handbook_version_id) VALUES
  -- Stripe (healthy)
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'engagement', 'ok',
   'Daily active usage up 12% this month', 'API calls increased from 2.3M to 2.6M daily', 'Continue monitoring',
   'gemini-2.0-flash', 'v1.0', 'abc123', '44444444-4444-4444-4444-444444444441'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'sentiment', 'ok',
   'Team sentiment is positive based on recent interactions', 'Patrick mentioned "couldn''t be happier" in last call',
   NULL, 'gemini-2.0-flash', 'v1.0', 'def456', '44444444-4444-4444-4444-444444444441'),

  -- Globex (at risk - triggers demo scenario)
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'engagement', 'risk',
   'Engagement dropped 40% in the last 2 weeks', 'Login frequency down, support tickets up',
   'Schedule executive check-in', 'gemini-2.0-flash', 'v1.0', 'ghi789', '44444444-4444-4444-4444-444444444441'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'sentiment', 'warn',
   'CFO inquired about downgrade options', 'Email from Sarah Chen asking about lighter plans',
   'Prepare value narrative before renewal discussion', 'gemini-2.0-flash', 'v1.0', 'jkl012', '44444444-4444-4444-4444-444444444441'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'commitments', 'risk',
   'Technical champion departed, commitments at risk', 'Frank Grimes left; his integrations are undocumented',
   'Urgent: find new technical contact', 'gemini-2.0-flash', 'v1.0', 'mno345', '44444444-4444-4444-4444-444444444441'),

  -- Acme Corp (onboarding)
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'engagement', 'ok',
   'Strong engagement during onboarding', 'Daily standups attended, questions being asked',
   NULL, 'gemini-2.0-flash', 'v1.0', 'pqr678', '44444444-4444-4444-4444-444444444441');

-- ============================================================================
-- NEEDS (Today Queue)
-- ============================================================================

INSERT INTO needs (id, workspace_id, customer_id, type, headline, lede, priority_rank, agent_reasoning, handbook_version_id) VALUES
  ('77777777-7777-7777-7777-777777777771', '11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665',
   'going_dark',
   'Globex engineering leadership gone quiet',
   'No response from technical team in 9 days',
   1,
   'Triggered by: engagement signal dropped to "risk" state. Technical champion Frank Grimes departed 2 weeks ago. Last email to engineering team sent 9 days ago with no response. This matches the "Going Dark" criteria in handbook: no response to 2+ outreach attempts over 7 days.',
   '44444444-4444-4444-4444-444444444441'),

  ('77777777-7777-7777-7777-777777777772', '11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665',
   'renewal_at_risk',
   'Globex CFO asking about downgrade options',
   'Multiple pricing inquiries suggest budget pressure',
   2,
   'CFO Sarah Chen sent 3 emails in the past week asking about: (1) lighter tier options, (2) per-seat vs flat pricing, (3) contract flexibility. Combined with engagement decline and champion departure, this account requires immediate attention per "Renewal Readiness" handbook section on At Risk indicators.',
   '44444444-4444-4444-4444-444444444442'),

  ('77777777-7777-7777-7777-777777777773', '11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666',
   'stalled_milestone',
   'Acme Corp blocked on API key generation',
   'Technical setup milestone overdue by 3 days',
   3,
   'Milestone "Technical Setup" was due on Day 14, now on Day 18. Last Slack message from Road Runner: "Still waiting on IT to provision the service account." This blocks the entire downstream timeline. Playbook suggests escalating to CTO if customer-side blocker exceeds 5 days.',
   '44444444-4444-4444-4444-444444444441'),

  ('77777777-7777-7777-7777-777777777774', '11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666664',
   'approaching_renewal',
   'Figma renewal in 28 days',
   'Strong signals but no formal commitment yet',
   5,
   'Renewal date: 28 days out. Renewal readiness: "ready" based on signals. However, no budget confirmation received. Handbook recommends starting renewal conversation at T-30 days for ready accounts.',
   '44444444-4444-4444-4444-444444444442'),

  ('77777777-7777-7777-7777-777777777775', '11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666667',
   'meeting_prep_ready',
   'Stark Industries kickoff call tomorrow',
   'Enterprise onboarding requires thorough prep',
   4,
   'Scheduled meeting: "Stark Industries Kickoff" tomorrow at 2pm. Enterprise archetype requires comprehensive stakeholder mapping and compliance discussion. MeetingPrepAgent should generate brief with security-focused talking points.',
   '44444444-4444-4444-4444-444444444443');

-- Add recommendations for needs
INSERT INTO need_recommendations (need_id, rationale, primary_action, secondary_action, confidence_text, model, prompt_version, handbook_version_id) VALUES
  ('77777777-7777-7777-7777-777777777771',
   'Based on the Going Dark playbook, we should try alternative channels before escalating.',
   'Send Slack DM to engineering team referencing the stalled communication',
   'If no response in 24h, escalate to VP Operations directly',
   'High confidence - matches playbook exactly',
   'gemini-2.0-flash', 'v1.0', '44444444-4444-4444-4444-444444444441'),

  ('77777777-7777-7777-7777-777777777772',
   'CFO inquiries about pricing often precede churn. Need to reframe value before renewal discussion.',
   'Schedule value review meeting with Hank Scorpio (champion) before CFO touchpoint',
   'Prepare ROI deck showing impact of Phase 1 deployment',
   'Medium confidence - need more context on budget situation',
   'gemini-2.0-flash', 'v1.0', '44444444-4444-4444-4444-444444444442'),

  ('77777777-7777-7777-7777-777777777773',
   'Customer-side blockers require gentle escalation to avoid blame dynamics.',
   'Draft email to Wile E. Coyote offering to help unblock IT provisioning',
   'Offer to join their internal IT call to explain requirements',
   'High confidence - standard onboarding playbook response',
   'gemini-2.0-flash', 'v1.0', '44444444-4444-4444-4444-444444444441');

-- ============================================================================
-- MILESTONES (for onboarding customers)
-- ============================================================================

INSERT INTO milestones (workspace_id, customer_id, title, owner_side, target_date, status, description, sort_order, adapted_from_playbook_id) VALUES
  -- Acme Corp milestones
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'Kickoff Call', 'us',
   CURRENT_DATE - INTERVAL '18 days', 'done',
   'Initial alignment on goals and timeline', 1, '55555555-5555-5555-5555-555555555551'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'Technical Setup', 'customer',
   CURRENT_DATE - INTERVAL '4 days', 'blocked',
   'API keys and environment configuration', 2, '55555555-5555-5555-5555-555555555551'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'Data Migration', 'joint',
   CURRENT_DATE + INTERVAL '3 days', 'not_started',
   'Historical data import', 3, '55555555-5555-5555-5555-555555555551'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'Go-Live', 'joint',
   CURRENT_DATE + INTERVAL '24 days', 'not_started',
   'Production deployment', 4, '55555555-5555-5555-5555-555555555551'),

  -- Stark Industries milestones
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666667', 'Executive Alignment', 'us',
   CURRENT_DATE + INTERVAL '2 days', 'in_progress',
   'C-level sponsor alignment', 1, '55555555-5555-5555-5555-555555555552'),
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666667', 'Security Review', 'customer',
   CURRENT_DATE + INTERVAL '16 days', 'not_started',
   'InfoSec review and approval', 2, '55555555-5555-5555-5555-555555555552');

-- ============================================================================
-- AGENT STATE (Watermarks for SignalWatcher)
-- ============================================================================

INSERT INTO agent_state (workspace_id, key, value) VALUES
  ('11111111-1111-1111-1111-111111111111', 'gmail_watermark', (NOW() - INTERVAL '15 minutes')::TEXT),
  ('11111111-1111-1111-1111-111111111111', 'slack_watermark', (NOW() - INTERVAL '15 minutes')::TEXT),
  ('11111111-1111-1111-1111-111111111111', 'notion_watermark', (NOW() - INTERVAL '15 minutes')::TEXT);

-- ============================================================================
-- DEMO DATA: Pending Handoff (TechCorp - ready for HandoffChain demo)
-- ============================================================================

-- This handoff brief represents a deal that just closed in Notion
-- The HandoffChain agent would create this, but we seed it for demo readiness
INSERT INTO handoff_briefs (
  id, workspace_id, customer_id, captured_at,
  sales_commitments, technical_context,
  reality_check_confidence, reality_check_risks,
  status, notion_deal_id, notion_deal_url,
  handbook_version_id, model, prompt_version
) VALUES (
  '88888888-8888-8888-8888-888888888881', '11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666668', NOW(),
  '[
    {"item": "30-day implementation timeline", "details": "CEO wants to launch before board meeting"},
    {"item": "Dedicated support channel", "details": "Slack Connect promised"},
    {"item": "Custom reporting dashboard", "details": "Weekly exec summary report"}
  ]'::jsonb,
  '[
    {"item": "REST API integration required", "details": "They use a custom CRM"},
    {"item": "SSO via Okta", "details": "Standard enterprise requirement"},
    {"item": "Data residency in US-East", "details": "Compliance requirement"}
  ]'::jsonb,
  'Medium confidence - timeline is aggressive but team seems capable',
  'The 30-day timeline is tight for custom CRM integration. Standard playbook suggests 42 days minimum. May need to scope down initial launch or increase engineering support.',
  'draft',
  'notion-deal-techcorp-001',
  'https://notion.so/deals/techcorp',
  '44444444-4444-4444-4444-444444444443', 'gemini-2.0-flash', 'v1.0'
);

-- Seed an AI plan for the handoff (pending approval)
INSERT INTO ai_plans (
  id, workspace_id, customer_id, brief_id,
  archetype_name, milestone_count, duration_label, rationale, headline,
  milestones,
  status, human_edited, regeneration_count,
  generated_at, model, prompt_version, inputs_hash, handbook_version_id
) VALUES (
  '99999999-9999-9999-9999-999999999991', '11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666668', '88888888-8888-8888-8888-888888888881',
  'Accelerated Mid-Market', 7, '35 days',
  'Based on TechCorp''s technical readiness and urgency, we recommend an accelerated timeline with parallel workstreams. The custom CRM integration is the critical path.',
  'Fast-track onboarding with parallel API and SSO workstreams',
  '[
    {"title": "Kickoff & Technical Discovery", "owner_side": "joint", "target_days": 3, "description": "Align on requirements, validate CRM API docs"},
    {"title": "SSO Configuration", "owner_side": "customer", "target_days": 7, "description": "Okta setup can run parallel to integration work"},
    {"title": "CRM Integration - Phase 1", "owner_side": "us", "target_days": 14, "description": "Core contact and deal sync"},
    {"title": "User Training", "owner_side": "us", "target_days": 21, "description": "Admin and end-user sessions"},
    {"title": "CRM Integration - Phase 2", "owner_side": "us", "target_days": 25, "description": "Custom reporting dashboard"},
    {"title": "UAT & Go-Live Prep", "owner_side": "customer", "target_days": 30, "description": "Final validation before launch"},
    {"title": "Go-Live", "owner_side": "joint", "target_days": 35, "description": "Production deployment and monitoring"}
  ]'::jsonb,
  'pending_approval', false, 0,
  NOW(), 'gemini-2.0-flash', 'v1.0', 'techcorp-001', '44444444-4444-4444-4444-444444444443'
);

-- Add a need for the plan approval
INSERT INTO needs (id, workspace_id, customer_id, type, headline, lede, priority_rank, agent_reasoning, handbook_version_id) VALUES
  ('77777777-7777-7777-7777-777777777776', '11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666668',
   'plan_approval_required',
   'TechCorp onboarding plan ready for review',
   'AI-generated plan needs your approval before milestones are created',
   1,
   'HandoffChain agent completed. Deal "TechCorp Solutions" closed in Notion with $50K ARR. Handoff brief extracted sales commitments (30-day timeline, custom CRM integration) and generated an accelerated 35-day onboarding plan. Timeline is 7 days shorter than standard playbook due to customer urgency. Requires human review of reality check risks before proceeding.',
   '44444444-4444-4444-4444-444444444443');

-- ============================================================================
-- HANDOFF OPEN QUESTIONS (for demo)
-- ============================================================================

INSERT INTO handoff_open_questions (id, brief_id, text, resolved) VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '88888888-8888-8888-8888-888888888881', 'What CRM system are they using? Need to validate API compatibility.', false),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab', '88888888-8888-8888-8888-888888888881', 'Is the 30-day timeline flexible if we hit integration blockers?', false),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaac', '88888888-8888-8888-8888-888888888881', 'Who is the day-to-day technical contact for the integration?', true);

-- ============================================================================
-- MEETINGS (Upcoming)
-- ============================================================================

INSERT INTO meetings (workspace_id, customer_id, title, type, scheduled_at, duration_minutes, source, attendees_ours, attendees_theirs) VALUES
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666667',
   'Stark Industries Kickoff Call', 'kickoff',
   NOW() + INTERVAL '1 day' + INTERVAL '14 hours', 60, 'google_calendar',
   '[{"name": "Sarah Chen", "role": "CSM"}, {"name": "Dev User", "role": "Solutions Engineer"}]'::jsonb,
   '[{"name": "Jordan Park", "email": "jordan@stark.com", "role": "VP Engineering"}]'::jsonb),

  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666663',
   'Notion Renewal Discussion', 'renewal',
   NOW() + INTERVAL '7 days', 45, 'manual',
   '[{"name": "Sarah Chen", "role": "CSM"}]'::jsonb,
   '[{"name": "Ivan Zhao", "email": "ivan@notion.so", "role": "CEO"}]'::jsonb);

-- ============================================================================
-- SAMPLE INTERACTIONS
-- ============================================================================

INSERT INTO interactions (workspace_id, customer_id, channel, direction, sender_name, occurred_at, subject, body_encrypted, summary_ai) VALUES
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'email', 'customer',
   'Sarah Chen', NOW() - INTERVAL '2 days',
   'Re: Q4 Contract Review',
   'Hi team, Before our renewal discussion, I wanted to understand our options. Is there a lighter tier that still includes SSO? We''re reviewing all vendor spend for next year. Thanks, Sarah',
   'CFO asking about downgrade options ahead of renewal'),

  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666665', 'email', 'us',
   'Sarah Chen (CSM)', NOW() - INTERVAL '9 days',
   'Following up on Phase 2 timeline',
   'Hi Frank, Just checking in on the Phase 2 integration work. We haven''t heard back on the API credentials issue. Let me know if you need any support from our side. Best, Sarah',
   'Follow-up email to technical champion - no response received'),

  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666666', 'slack', 'customer',
   'Road Runner', NOW() - INTERVAL '1 day',
   NULL,
   'Hey! Quick update - still waiting on IT to provision the service account. They said "by end of week" but no promises. Is there anything we can do to unblock this on your end?',
   'Customer blocked on internal IT provisioning for API setup'),

  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'meeting', 'internal',
   NULL, NOW() - INTERVAL '7 days',
   'Stripe Quarterly Business Review',
   'Attendees: Patrick Collison, David Singleton, Sarah Chen (us). Discussed: API usage growth (+12%), upcoming features roadmap, expansion into new markets. Patrick mentioned they "couldn''t be happier with the partnership."',
   'Positive QBR with executive sponsor expressing satisfaction'),

  -- More Stripe interactions for demo
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'email', 'customer',
   'David Singleton', NOW() - INTERVAL '8 hours',
   'Re: New reporting dashboard access',
   'Got it working! The team is already finding value in the custom reports. Quick question - can we add role-based permissions to limit who sees revenue data?',
   'CISO requesting access control features for reporting dashboard'),

  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'slack', 'customer',
   'Patrick Collison', NOW() - INTERVAL '2 hours',
   NULL,
   'Just wanted to flag - our team is loving the new batch processing. The engineering sync next week should be interesting.',
   'CEO positive feedback on batch processing feature'),

  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666661', 'meeting', 'us',
   NULL, NOW() - INTERVAL '5 hours',
   'Engineering sync call',
   'Weekly engineering sync. Discussed API rate limit increases and upcoming webhook improvements.',
   'Engineering sync - discussed rate limits and webhooks'),

  -- More TechCorp interactions
  ('11111111-1111-1111-1111-111111111111', '66666666-6666-6666-6666-666666666667', 'email', 'us',
   'Alex (CSM)', NOW() - INTERVAL '1 day',
   'Welcome to Herofy - Kickoff scheduled',
   'Hi Maria, Welcome aboard! I''ve scheduled our kickoff call for tomorrow at 2pm. Looking forward to getting TechCorp set up for success.',
   'Kickoff email sent to new customer');
