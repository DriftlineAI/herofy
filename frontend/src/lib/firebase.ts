import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
import { getDataConnect, connectDataConnectEmulator } from "firebase/data-connect";
import {
  getAuth,
  connectAuthEmulator,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInAnonymously,
  signOut as firebaseSignOut,
  onAuthStateChanged,
  type User
} from "firebase/auth";
// Import the SDK's connectorConfig so we can connect IT to the emulator too
import { connectorConfig } from '@/dataconnect-generated';

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyBGjQ9uT5oa38DuxFgfU8amBhOZRLN-9gM",
  authDomain: "herofy-496505.firebaseapp.com",
  projectId: "herofy-496505",
  storageBucket: "herofy-496505.firebasestorage.app",
  messagingSenderId: "620187851999",
  appId: "1:620187851999:web:552ca980870afa392e5d6a",
  measurementId: "G-HTVXW5LZSS"
};

// Initialize Firebase
export const app = initializeApp(firebaseConfig);
export const analytics = getAnalytics(app);

// Initialize Auth
export const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

// Initialize Data Connect using the SDK's connectorConfig for consistency
// This ensures we get the SAME cached instance the generated SDK uses
export const dataConnect = getDataConnect(app, connectorConfig);

// Connect to emulators in development (set VITE_USE_EMULATOR=true to enable)
if (import.meta.env.DEV && import.meta.env.VITE_USE_EMULATOR === 'true') {
  connectDataConnectEmulator(dataConnect, "localhost", 9399);
  // Uncomment to use Auth emulator:
  // connectAuthEmulator(auth, "http://localhost:9099");
  console.log("Connected to Data Connect emulator");
} else if (import.meta.env.DEV) {
  console.log("Using production Data Connect (CloudSQL)");
}

// Auth helper functions
export const signInWithGoogle = () => signInWithPopup(auth, googleProvider);

export const signInWithEmail = (email: string, password: string) =>
  signInWithEmailAndPassword(auth, email, password);

export const signUpWithEmail = (email: string, password: string) =>
  createUserWithEmailAndPassword(auth, email, password);

export const signOut = () => firebaseSignOut(auth);

// Anonymous sign-in for the per-visitor demo sandbox (demo.herofy.ai). Only called from the
// /demo landing; the prod app bounces anonymous users (see RequireAuth).
export const signInAnon = () => signInAnonymously(auth);

export { onAuthStateChanged, type User };
