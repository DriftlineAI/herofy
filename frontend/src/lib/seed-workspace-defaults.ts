/**
 * Seeds default content when a new workspace is created.
 * This ensures every workspace starts with playbooks, handbook docs, and voice docs.
 */

import { v5 as uuidv5 } from 'uuid';

// Namespace UUID for generating deterministic IDs
// This ensures the same workspace + slug always produces the same ID
const HEROFY_NAMESPACE = '6ba7b810-9dad-11d1-80b4-00c04fd430c8';
import {
  createPlaybookWithId,
  createPlaybookMilestoneWithId,
  createHandbookDocWithId,
  OwnerSide,
  BlastRadius,
  HandbookDocKind,
} from '@herofy/dataconnect';
import { dataConnect } from './firebase';
import {
  DEFAULT_PLAYBOOKS,
  DEFAULT_HANDBOOK_DOCS,
  DEFAULT_VOICE_DOCS,
} from './workspace-defaults';

// Helper to map string literals to SDK enum values
const ownerSideMap: Record<string, OwnerSide> = {
  us: OwnerSide.us,
  customer: OwnerSide.customer,
  joint: OwnerSide.joint,
};

const blastRadiusMap: Record<string, BlastRadius> = {
  low: BlastRadius.low,
  medium: BlastRadius.medium,
  high: BlastRadius.high,
};

const handbookDocKindMap: Record<string, HandbookDocKind> = {
  DOCUMENT: HandbookDocKind.DOCUMENT,
  VOICE_CORE: HandbookDocKind.VOICE_CORE,
  VOICE_FOUNDATION: HandbookDocKind.VOICE_FOUNDATION,
  VOICE_SCENARIO: HandbookDocKind.VOICE_SCENARIO,
};

/**
 * Seeds all default content for a newly created workspace.
 * This is called automatically during workspace provisioning.
 *
 * Errors are logged but not thrown - we don't want seeding failures
 * to block workspace creation. Missing defaults can be added later.
 */
export async function seedWorkspaceDefaults(workspaceId: string): Promise<void> {
  console.log('[seedWorkspaceDefaults] Starting for workspace:', workspaceId);

  // Seed in parallel for speed
  await Promise.all([
    seedPlaybooks(workspaceId),
    seedHandbookDocs(workspaceId),
    seedVoiceDocs(workspaceId),
  ]);

  console.log('[seedWorkspaceDefaults] Complete');
}

async function seedPlaybooks(workspaceId: string): Promise<void> {
  for (const playbook of DEFAULT_PLAYBOOKS) {
    // Deterministic ID: same workspace + playbook name = same ID (idempotent)
    const playbookSlug = playbook.name.toLowerCase().replace(/\s+/g, '-');
    const playbookId = uuidv5(`${workspaceId}:playbook:${playbookSlug}`, HEROFY_NAMESPACE);

    try {
      await createPlaybookWithId(dataConnect, {
        id: playbookId,
        workspaceId,
        name: playbook.name,
        archetype: playbook.archetype,
        fitNote: playbook.fitNote,
      });
      console.log(`[seedWorkspaceDefaults] Created playbook: ${playbook.name}`);

      // Create milestones for this playbook
      for (const milestone of playbook.milestones) {
        const milestoneSlug = milestone.title.toLowerCase().replace(/\s+/g, '-');
        const milestoneId = uuidv5(`${playbookId}:milestone:${milestoneSlug}`, HEROFY_NAMESPACE);

        try {
          await createPlaybookMilestoneWithId(dataConnect, {
            id: milestoneId,
            playbookId,
            title: milestone.title,
            ownerSide: ownerSideMap[milestone.ownerSide],
            durationDays: milestone.durationDays,
            description: milestone.description,
            sortOrder: milestone.sortOrder,
          });
        } catch (err) {
          // Ignore "already exists" errors - this makes the operation idempotent
          const errorMsg = err instanceof Error ? err.message : String(err);
          if (!errorMsg.includes('ALREADY_EXISTS') && !errorMsg.includes('duplicate')) {
            console.warn(`[seedWorkspaceDefaults] Failed to create milestone ${milestone.title}:`, err);
          }
        }
      }
    } catch (err) {
      // Ignore "already exists" errors - this makes the operation idempotent
      const errorMsg = err instanceof Error ? err.message : String(err);
      if (!errorMsg.includes('ALREADY_EXISTS') && !errorMsg.includes('duplicate')) {
        console.warn(`[seedWorkspaceDefaults] Failed to create playbook ${playbook.name}:`, err);
      }
    }
  }
}

async function seedHandbookDocs(workspaceId: string): Promise<void> {
  for (const doc of DEFAULT_HANDBOOK_DOCS) {
    // Deterministic ID: same workspace + slug = same ID (idempotent)
    const docId = uuidv5(`${workspaceId}:handbook:${doc.slug}`, HEROFY_NAMESPACE);

    try {
      await createHandbookDocWithId(dataConnect, {
        id: docId,
        workspaceId,
        slug: doc.slug,
        title: doc.title,
        description: doc.description,
        body: doc.body,
        blastRadius: blastRadiusMap[doc.blastRadius],
      });
      console.log(`[seedWorkspaceDefaults] Created handbook doc: ${doc.slug}`);
    } catch (err) {
      // Ignore "already exists" errors - this makes the operation idempotent
      const errorMsg = err instanceof Error ? err.message : String(err);
      if (!errorMsg.includes('ALREADY_EXISTS') && !errorMsg.includes('duplicate')) {
        console.warn(`[seedWorkspaceDefaults] Failed to create handbook doc ${doc.slug}:`, err);
      }
    }
  }
}

async function seedVoiceDocs(workspaceId: string): Promise<void> {
  for (const doc of DEFAULT_VOICE_DOCS) {
    // Deterministic ID: same workspace + slug = same ID (idempotent)
    const docId = uuidv5(`${workspaceId}:voice:${doc.slug}`, HEROFY_NAMESPACE);

    try {
      await createHandbookDocWithId(dataConnect, {
        id: docId,
        workspaceId,
        slug: doc.slug,
        title: doc.title,
        description: doc.description,
        body: doc.body,
        blastRadius: blastRadiusMap[doc.blastRadius],
        kind: handbookDocKindMap[doc.kind],
        pinned: doc.pinned,
        chapterNum: doc.chapterNum,
        affectsSurfaces: doc.affectsSurfaces,
      });
      console.log(`[seedWorkspaceDefaults] Created voice doc: ${doc.slug}`);
    } catch (err) {
      // Ignore "already exists" errors - this makes the operation idempotent
      const errorMsg = err instanceof Error ? err.message : String(err);
      if (!errorMsg.includes('ALREADY_EXISTS') && !errorMsg.includes('duplicate')) {
        console.warn(`[seedWorkspaceDefaults] Failed to create voice doc ${doc.slug}:`, err);
      }
    }
  }
}
