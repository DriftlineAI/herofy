"""
HandoffChain Prompts
Prompt templates for agent steps
"""

GAP_ANALYSIS_PROMPT = """You are a Customer Success expert analyzing a new deal handoff.

## Deal Information
Company: {company_name}
ARR: ${arr_display}
Timeline expectation: {timeline}

## Sales Commitments Made
{commitments_list}

## Technical Requirements
{technical_list}

## Additional Context (from Notion/Sales Notes)
{notes_context}

## Playbook Baseline
Playbook: {playbook_name}
Archetype: {playbook_archetype}
Standard duration: {playbook_duration} days
Number of milestones: {milestone_count}

## Standard Milestones
{milestones_list}

## Your Task
Analyze the gap between sales commitments and the standard playbook. Consider:
1. Is the promised timeline realistic given the playbook norms?
2. Are there technical requirements that could extend the timeline?
3. What risks should the CSM be aware of?
4. What questions need to be answered before onboarding begins?

Respond in JSON format:
{{
    "confidence": "high|medium|low",
    "timeline_feasible": true|false,
    "risks": ["risk 1", "risk 2", ...],
    "recommendations": ["recommendation 1", "recommendation 2", ...],
    "open_questions": ["question 1", "question 2", ...]
}}
"""

PLAN_GENERATION_PROMPT = """You are a Customer Success expert creating an onboarding plan.

## Deal Context
Company: {company_name}
ARR: ${arr_display}
Timeline expectation: {timeline}

## Sales Commitments
{commitments_list}

## Additional Context
{notes_context}

## Gap Analysis Summary
Confidence: {gap_confidence}
Timeline feasible: {timeline_feasible}
Key risks:
{risks_list}

## Playbook Template
Playbook: {playbook_name}
Standard milestones:
{milestones_list}

## Your Task
Create a customized onboarding plan that FITS THE CUSTOMER'S TIMELINE.

The playbook template is a STARTING POINT. You MUST adapt it to match:
- The customer's stated timeline ({timeline})
- Their technical complexity
- Their team availability

You MAY:
- Add milestones not in the template
- Remove milestones that don't apply
- Significantly compress or extend durations
- Create entirely custom timelines if needed

NEVER respond that you can't create a plan. Always generate the best plan possible.

Each milestone should indicate its source:
- "block:<slug>" if adapted from a catalog block
- "template" if from the playbook template
- "custom" if created specifically for this customer

Respond in JSON format:
{{
    "headline": "Short 1-line summary of the plan approach",
    "rationale": "2-3 sentences explaining why this plan was created this way",
    "based_on": "template:<playbook-name>",
    "milestones": [
        {{
            "title": "Milestone name",
            "owner_side": "us|customer|joint",
            "target_days": <number of days from start>,
            "description": "What needs to happen in this milestone",
            "source": "template|block:<slug>|custom"
        }},
        ...
    ]
}}
"""

NEED_REASONING_TEMPLATE = """HandoffChain agent completed successfully.

## Deal Summary
- Company: {company_name}
- ARR: ${arr_display}
- Source: Notion deal {notion_deal_id}

## What Was Generated
1. **Handoff Brief** (ID: {brief_id})
   - Captured {commitment_count} sales commitments
   - Captured {technical_count} technical requirements
   - Reality check confidence: {confidence}

2. **Onboarding Plan** (ID: {plan_id})
   - Based on: {playbook_name} playbook
   - {milestone_count} milestones over {duration}
   - Status: Pending approval

## Why This Requires Attention
{risks_summary}

## Recommended Action
Review the generated onboarding plan and handoff brief. Approve if the milestones and timeline are appropriate, or edit to adjust based on your knowledge of the customer.
"""
