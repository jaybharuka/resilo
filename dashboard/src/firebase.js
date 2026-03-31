import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';
import { getAnalytics } from 'firebase/analytics';

const firebaseConfig = {
  apiKey:            process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain:        process.env.REACT_APP_FIREBASE_AUTH_DOMAIN        || "resilo-ai.firebaseapp.com",
  projectId:         process.env.REACT_APP_FIREBASE_PROJECT_ID         || "resilo-ai",
  storageBucket:     process.env.REACT_APP_FIREBASE_STORAGE_BUCKET     || "resilo-ai.firebasestorage.app",
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID || "156159850720",
  appId:             process.env.REACT_APP_FIREBASE_APP_ID             || "1:156159850720:web:126fe7d7b912dc47c17885",
  measurementId:     process.env.REACT_APP_FIREBASE_MEASUREMENT_ID     || "G-6YP1EFQ6GJ",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const analytics = getAnalytics(app);
export default app;
