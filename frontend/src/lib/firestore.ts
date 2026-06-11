/**
 * Firestore client for real-time subscriptions
 *
 * Used for streaming updates during:
 * - Setup flow (customer classification progress)
 * - Agent execution status
 * - Workspace notifications
 */

import { getFirestore, connectFirestoreEmulator } from 'firebase/firestore';

// Import app directly - this ensures firebase.ts runs first and initializes the app
import { app } from './firebase';

export const db = getFirestore(app);

// Connect to emulator in development (port 8181 to avoid conflict with DataConnect on 8080)
if (import.meta.env.DEV) {
  try {
    connectFirestoreEmulator(db, 'localhost', 8181);
    console.log('Connected to Firestore emulator on port 8181');
  } catch (e) {
    // Emulator already connected or not available
    console.log('Firestore emulator connection skipped:', e);
  }
}
