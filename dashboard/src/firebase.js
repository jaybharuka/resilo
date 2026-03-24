import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';
import { getAnalytics } from 'firebase/analytics';

const firebaseConfig = {
  apiKey:            "AIzaSyDR-PIwkQL76-Yyr9NP68IDJlii3zYZkuw",
  authDomain:        "resilo-ai.firebaseapp.com",
  projectId:         "resilo-ai",
  storageBucket:     "resilo-ai.firebasestorage.app",
  messagingSenderId: "156159850720",
  appId:             "1:156159850720:web:126fe7d7b912dc47c17885",
  measurementId:     "G-6YP1EFQ6GJ",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const analytics = getAnalytics(app);
export default app;
