// Thin wrappers around localStorage -- never store anything sensitive
// beyond the JWT itself (never a quiz answer key, never a raw password).
// Every call is wrapped in try/catch: a private-browsing tab or blocked
// site data can make localStorage throw on read/write, and the app should
// degrade (treat as "nothing stored") rather than crash.

export function getItem(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function setItem(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* ignore -- see module note */
  }
}

export function removeItem(key) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}
