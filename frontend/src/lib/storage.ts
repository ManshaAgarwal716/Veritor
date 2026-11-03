/**
 * Storage helpers for local scan history and monitored package watchlist.
 *
 * Provides unified synchronization between backend API (primary source of truth)
 * and localStorage (fallback and offline cache), preventing silent divergence.
 */

import {
  addToWatchlist as apiAddToWatchlist,
  getWatchlist as apiGetWatchlist,
  removeFromWatchlist as apiRemoveFromWatchlist,
} from "./api";
import { Ecosystem, ScanHistoryItem, WatchlistItem } from "./types";

const HISTORY_KEY = "veritor_scan_history_v1";
const WATCHLIST_KEY = "veritor_watchlist_v1";
const MAX_HISTORY = 50;

export function getScanHistory(): ScanHistoryItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveScanToHistory(item: ScanHistoryItem): void {
  if (typeof window === "undefined") return;
  try {
    const current = getScanHistory();
    // Deduplicate by scan_id
    const filtered = current.filter((h) => h.scan_id !== item.scan_id);
    const updated = [item, ...filtered].slice(0, MAX_HISTORY);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
    window.dispatchEvent(new Event("veritor_history_updated"));
  } catch {
    // LocalStorage quota or disabled
  }
}

export function clearScanHistory(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(HISTORY_KEY);
    window.dispatchEvent(new Event("veritor_history_updated"));
  } catch {
    // Ignore
  }
}

/**
 * Local cache accessor for watchlist items.
 */
export function getWatchlist(): WatchlistItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Helper to update local cache and broadcast update event.
 */
function setLocalWatchlist(items: WatchlistItem[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items));
    window.dispatchEvent(new Event("veritor_watchlist_updated"));
  } catch {
    // Ignore storage quota errors
  }
}

/**
 * Synchronize watchlist with backend API (primary source of truth).
 * Updates localStorage cache to avoid silent state divergence.
 * Falls back gracefully to local cache when backend is unavailable.
 */
export async function syncWatchlist(): Promise<WatchlistItem[]> {
  try {
    const remoteItems = await apiGetWatchlist();
    if (Array.isArray(remoteItems)) {
      setLocalWatchlist(remoteItems);
      return remoteItems;
    }
  } catch {
    // Backend unavailable / offline: return local cache
  }
  return getWatchlist();
}

/**
 * Add package to watchlist.
 * Prioritizes backend API persistence and keeps localStorage synchronized.
 */
export async function addWatchlistItem(req: {
  ecosystem: Ecosystem;
  package_name: string;
  notes?: string;
}): Promise<WatchlistItem> {
  try {
    const created = await apiAddToWatchlist(req);
    const current = getWatchlist().filter((w) => w.id !== created.id);
    const updated = [created, ...current];
    setLocalWatchlist(updated);
    return created;
  } catch {
    // Fallback: persist locally if backend API call fails
    return addToWatchlist(req);
  }
}

/**
 * Remove package from watchlist.
 * Deletes from backend API (if available) and removes from local cache.
 */
export async function removeWatchlistItem(id: string): Promise<void> {
  try {
    await apiRemoveFromWatchlist(id);
  } catch {
    // Fallback if backend unavailable
  }
  removeFromWatchlist(id);
}

/**
 * Synchronous local addition fallback.
 */
export function addToWatchlist(item: Omit<WatchlistItem, "id" | "added_at">): WatchlistItem {
  const current = getWatchlist();
  const existing = current.find(
    (w) =>
      w.ecosystem === item.ecosystem &&
      w.package_name.toLowerCase() === item.package_name.toLowerCase()
  );
  if (existing) {
    return existing;
  }
  const newItem: WatchlistItem = {
    ...item,
    id: `${item.ecosystem}:${item.package_name}`,
    added_at: new Date().toISOString(),
  };
  const updated = [newItem, ...current];
  setLocalWatchlist(updated);
  return newItem;
}

export function removeFromWatchlist(id: string): void {
  const current = getWatchlist();
  const updated = current.filter((w) => w.id !== id);
  setLocalWatchlist(updated);
}

export function updateWatchlistItem(
  id: string,
  updates: Partial<Omit<WatchlistItem, "id" | "ecosystem" | "package_name">>
): void {
  const current = getWatchlist();
  const updated = current.map((w) => (w.id === id ? { ...w, ...updates } : w));
  setLocalWatchlist(updated);
}
