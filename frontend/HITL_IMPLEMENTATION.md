# HITL (Human-in-the-Loop) Frontend Implementation

## Overview

Implemented the rich HITL question UI from Claude Design export, replacing the generic textarea approach with sophisticated question types that match the design aesthetic.

## Files Created/Modified

### New Components

**`src/components/sidekick/HITLComponents.tsx`**
- `HITLChip` - Squared-off chips with rust-tinted selection states
- `HITLQuestion` - Question wrapper with numbered serif-italic gutter
- `HITLPickOne` - Single-select chips with radio buttons + "Sidekick, you decide" option
- `HITLPickMany` - Multi-select chips with checkboxes
- `HITLPickPerson` - Avatar-rich person selector for contact/champion questions
- `HITLSlider` - Rust-colored slider with custom labels and formatting
- `HITLFreeform` - Editorial underline textarea for prose answers

### Updated Pages

**`src/pages/SidekickQuestion.tsx`**
- Complete redesign matching Claude Design HITL screens
- Editorial Playfair-inspired typography
- Batched question presentation with numbered gutters
- Progress indicators and "why this batch" context
- Supports all 5 question types dynamically

### Updated Types

**`src/lib/api.ts`**
- Added `QuestionType` enum
- Added `QuestionOption` interface for pick_one/pick_many
- Added `PersonOption` interface for pick_person
- Enhanced `AgentQuestion` with `question_type` and `metadata` fields

## Question Types Supported

### 1. Pick One (Single Select)
```typescript
{
  question_type: 'pick_one',
  metadata: {
    options: [
      { label: "Firm milestone", value: "firm", default: true },
      { label: "Target", value: "target" },
      { label: "Aspiration", value: "aspiration" }
    ],
    allow_decide: true,
    allow_other: true,
    decide_label: "Sidekick, you decide"
  }
}
```

### 2. Pick Many (Multi Select)
```typescript
{
  question_type: 'pick_many',
  metadata: {
    options: [
      { label: "SSO configured", value: "sso", default: true },
      { label: "API integration live", value: "api" }
    ],
    allow_other: true
  }
}
```

### 3. Pick Person
```typescript
{
  question_type: 'pick_person',
  metadata: {
    people: [
      {
        stakeholder_id: "uuid",
        name: "Alice Johnson",
        role: "CEO",
        avatar_seed: "alice",
        signal: "ok",
        signal_label: "ENGAGED",
        last_contact: "2h ago · email"
      }
    ],
    allow_decide: true,
    allow_manual: true
  }
}
```

### 4. Slider
```typescript
{
  question_type: 'slider',
  metadata: {
    min: 3,
    max: 21,
    default: 7,
    label_low: "Aggressive · 3d",
    label_high: "Patient · 21d",
    format_template: "{value} day{s} of silence"
  }
}
```

### 5. Freeform
```typescript
{
  question_type: 'freeform',
  metadata: {}  // No special config needed
}
```

## Design Aesthetic

Following the Claude Design export:

- **Typography**: Playfair-inspired serif for titles, clean sans for body
- **Colors**: Charcoal background (#0F0D0C), cream text (#F5F1ED), rust accents (#C84B31)
- **Question Numbers**: Large serif-italic numerals (40px) in rust/40% opacity
- **Chips**: 2px border radius, rust border on selection, 10% rust background fill
- **Spacing**: Generous whitespace, 48px question separation
- **Progressive Disclosure**: "Sidekick, you decide" and "Other" options for flexibility

## Backward Compatibility

The implementation gracefully handles legacy questions:

1. If `question_type` is provided → use it
2. If missing → parse from `field_hint` (e.g., "PICK ONE" → pick_one)
3. If `metadata` is missing → use empty defaults

No frontend mock data - all data comes from backend/database.

## Backend Integration Points

The backend needs to provide:

1. **Database Schema**: Add `question_type` (enum) and `metadata` (JSONB) columns to `agent_questions` table
2. **Question Generation**: Python code to create structured questions with proper metadata
3. **Data Seeding**: Seed database with example questions for testing

See backend documentation for implementation details.

## Next Steps

1. Backend team implements question generation with structured metadata
2. Seed database with example HITL questions
3. Test all 5 question types in the UI
4. Add animation/transitions for question reveal
5. Implement answer validation (optional fields, required fields, etc.)
