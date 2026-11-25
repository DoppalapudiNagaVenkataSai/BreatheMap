/**
 * State persistence with safe localStorage fallback
 */
export const state = {
  get(key, defaultVal = null) {
    try {
      const v = localStorage.getItem(key);
      return v ? JSON.parse(v) : defaultVal;
    } catch (e) {
      return defaultVal;
    }
  },
  set(key, val) {
    try {
      localStorage.setItem(key, JSON.stringify(val));
    } catch (e) {
      // safe fallback if storage is blocked
    }
  },
};

export const KEYS = {
  LOCATION: "bm.location",
  SCALE: "bm.scale",
  SENSITIVE: "bm.sensitive",
  DEMO: "bm.demo",
};
