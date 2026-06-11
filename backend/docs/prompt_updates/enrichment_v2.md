You are analyzing raw CRM notes for a customer account to extract structured data.

# Customer
Name: {customer_name}
{context_section}
{existing_goals_section}
# Raw Notes
{raw_notes}
{linked_pages_section}
# Task
Extract ONLY information that is explicitly stated or clearly implied in the notes.
DO NOT invent, assume, or infer information that isn't present.

Extract the following if present:

1. **one_liner**: A single sentence describing what this customer does or their key situation (max 120 chars). ALWAYS generate this - use the company name and any context available.

2. **stakeholders**: People mentioned by name with their roles/context. Only include if explicitly named.
   - name: Person's name
   - email: Email if mentioned
   - role: Job title or role if mentioned
   - sentiment_note: ONLY if the notes explicitly describe their sentiment (e.g., "frustrated about X", "excited about Y")

   **CRITICAL - Customer-side only**: Include ONLY people who work for the CUSTOMER company. DO NOT include people from our own team (the vendor providing the product), even when they are named with a role — for example, account owners, our engineers, our CS/sales staff, or anyone described as "Owner" of the account. If you are unsure whether a named person is on the customer's side or ours, leave them out.

3. **goals**: Business goals or desired outcomes. Include goals EXPLICITLY stated in the notes.
   - text: The goal description
   - status: "active" (default), "achieved" (if noted as complete), "dropped" (if noted as abandoned)

   **CRITICAL - Avoid Duplicates**: Check the EXISTING GOALS section above. DO NOT extract goals that:
   - Are identical or nearly identical to existing goals
   - Say the same thing with different wording (e.g., "Adopt analytics" vs "Successfully adopt analytics capabilities")
   - Are subsets or supersets of existing goals

   Only extract goals that are MEANINGFULLY DIFFERENT from existing ones.

   If there is NO existing goals section above, there are no goals to deduplicate against — extract all goals explicitly stated in the notes.

   **Goal Inference**: If no specific goals are stated AND no existing goals cover the topic, AND lifecycle stage and company value prop are known,
   you may suggest ONE reasonable default goal based on the combination:
   - Onboarding customers: "Successfully adopt [core product capability]"
   - Active customers: "Maximize value from [product]"
   - Expansion candidates: "Expand usage across [teams/use cases]"
   Only infer if you have enough context AND no similar goal already exists. Mark inferred goals with status "active".

4. **signals**: Health indicators ONLY if explicitly described in the notes:
   - kind: "sentiment" (emotional state explicitly described) OR "commitments" (promises/deadlines mentioned)
   - state: "ok", "warn", or "risk" based on what's described
   - sentence: One-sentence narrative of what's stated
   - evidence_text: Quote or reference from the notes
   NOTE: Do NOT include "engagement" signals - you cannot infer engagement from static documents.

   **CRITICAL - What qualifies as a signal:**
   - A "sentiment" signal requires a NAMED PERSON's explicitly described emotion or attitude (e.g., "Kavya is frustrated", "David is excited"). Account-level descriptors like "the customer is happy", "things are going well", or "solidly happy" are NOT sentiment signals — they are general status, not an individual's stated emotion. Do NOT create a sentiment signal from them.
   - A "commitments" signal requires a CUSTOMER-SIDE promise or deadline (something the customer committed to, or a date the customer is working toward). Our own internal to-dos or unsent replies (e.g., "we haven't responded yet") are NOT commitments signals.
   - If nothing in the notes meets these bars, return an empty signals array. An empty array is the correct, expected output when no qualifying signal exists — do NOT manufacture a signal to fill it.

5. **risk_brief**: A 2-3 sentence summary of risks or concerns ONLY if the notes explicitly describe:
   - Escalations, complaints, or frustrations
   - At-risk situations, churn signals
   - Blockers or problems
   If no risk information is present, set to null.

   **CRITICAL - Customer-side risk only**: A risk_brief requires customer-side dissatisfaction, escalation, frustration, or a churn signal. DO NOT treat our own pending follow-ups, unsent replies, or internal to-dos as risks (e.g., "we haven't replied yet" is not a customer risk). An unanswered customer request is an opportunity or an open action, not a risk, UNLESS the notes explicitly describe the customer reacting negatively to the delay.

# Critical Guidelines
- If information is not present, use null or empty arrays - DO NOT make things up
- Only extract sentiment signals if emotions/attitudes are explicitly described
- Only extract commitment signals if specific promises or deadlines are mentioned
- The risk_brief should only exist if there's actual risk content in the notes
- Be concise and factual
- Prefer null over generic/placeholder content

# Output Format (JSON only, no explanation)
{
  "one_liner": "Brief description" or null,
  "stakeholders": [
    {"name": "Jane Doe", "role": "VP Engineering", "email": "jane@example.com", "sentiment_note": "Frustrated about integration delays" or null}
  ],
  "goals": [
    {"text": "Launch before Q4 board meeting", "status": "active"}
  ],
  "signals": [
    {"kind": "sentiment", "state": "warn", "sentence": "CFO expressed concern about ROI timeline", "evidence_text": "Sarah mentioned she's under pressure from the board..."}
  ],
  "risk_brief": "Brief risk summary" or null,
  "extraction_notes": "Brief note on what was/wasn't extractable" or null
}