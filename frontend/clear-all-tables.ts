/**
 * Clear ALL data in the local DataConnect and Firestore emulators
 *
 * ⚠️  LOCAL EMULATORS ONLY - Cannot connect to production!
 *
 * Run with: cd frontend && npx tsx clear-all-tables.ts
 *
 * This script:
 * 1. Deletes the PGLite data directory (DataConnect emulator's embedded PostgreSQL)
 * 2. Clears Firestore emulator collections (setup_progress, notifications, agent_status)
 *
 * After running, restart the DataConnect emulator to recreate empty tables.
 */

import { rmSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { initializeApp } from 'firebase/app';
import { getFirestore, connectFirestoreEmulator, collection, getDocs, deleteDoc, doc } from 'firebase/firestore';

// ES module equivalent of __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ============================================================================
// SAFETY: Local emulators only!
// ============================================================================
// PGLite data: ../dataconnect/.dataconnect/pgliteData (local files)
// Firestore: localhost:8181 (Firestore emulator)
//
// These are ONLY available when running the Firebase emulator suite locally.
// Production databases are NOT accessible via these paths/ports.
// ============================================================================

console.log('🔒 LOCAL EMULATORS ONLY - This script cannot affect production\n');

// Path to PGLite data directory (relative to frontend/)
const PGLITE_DATA_DIR = resolve(__dirname, '../dataconnect/.dataconnect/pgliteData');

// Initialize Firebase for Firestore clearing - EMULATOR ONLY
const firebaseConfig = { projectId: 'herofy-496505' };
const app = initializeApp(firebaseConfig);
const firestore = getFirestore(app);

// Connect to Firestore emulator on port 8181 (from firebase.json)
connectFirestoreEmulator(firestore, 'localhost', 8181);

// Firestore collections to clear
const FIRESTORE_COLLECTIONS = [
  'setup_progress',
  'notifications',
  'agent_status',
];

async function clearPGLiteData() {
  console.log('🗄️  Clearing DataConnect PGLite data...\n');
  console.log(`   Path: ${PGLITE_DATA_DIR}\n`);

  if (!existsSync(PGLITE_DATA_DIR)) {
    console.log('   - Directory does not exist (already clean)\n');
    return;
  }

  try {
    rmSync(PGLITE_DATA_DIR, { recursive: true, force: true });
    console.log('   ✓ PGLite data directory deleted!\n');
    console.log('   ⚠️  Restart the DataConnect emulator to recreate tables:\n');
    console.log('      firebase emulators:start --only dataconnect --project herofy-496505\n');
  } catch (e: any) {
    console.log(`   ✗ Failed to delete: ${e.message}\n`);
  }
}

async function clearFirestore() {
  console.log('🔥 Clearing Firestore emulator collections (port 8181)...\n');

  for (const collectionName of FIRESTORE_COLLECTIONS) {
    try {
      const colRef = collection(firestore, collectionName);
      const snapshot = await getDocs(colRef);

      if (snapshot.empty) {
        console.log(`   - ${collectionName} (empty)`);
        continue;
      }

      let count = 0;
      for (const docSnap of snapshot.docs) {
        await deleteDoc(doc(firestore, collectionName, docSnap.id));
        count++;
      }
      console.log(`   ✓ ${collectionName} (${count} docs deleted)`);
    } catch (e: any) {
      if (e.message?.includes('ECONNREFUSED')) {
        console.log(`   - ${collectionName} (emulator not running)`);
      } else {
        console.log(`   ✗ ${collectionName}: ${e.message}`);
      }
    }
  }
}

async function main() {
  // Clear PGLite data (DataConnect)
  await clearPGLiteData();

  // Clear Firestore
  await clearFirestore();

  console.log('\n✨ Database reset complete!');
  console.log('\nNext steps:');
  console.log('  1. Restart emulators: firebase emulators:start --only dataconnect,firestore --project herofy-496505');
  console.log('  2. Run seed-data.ts to repopulate: npx tsx seed-data.ts');
  console.log('  3. Or start fresh with the Setup flow\n');

  process.exit(0);
}

main();
