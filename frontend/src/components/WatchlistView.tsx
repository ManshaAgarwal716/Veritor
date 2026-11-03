"use client";

import React, { useState } from "react";
import {
  Bookmark,
  BookmarkPlus,
  Trash2,
  Search,
  Plus,
  RefreshCw,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import { checkWatchlistUpdates } from "../lib/api";
import {
  addWatchlistItem,
  removeWatchlistItem,
} from "../lib/storage";
import { Ecosystem, WatchlistItem } from "../lib/types";

interface WatchlistViewProps {
  watchlist: WatchlistItem[];
  onTriggerScan: (ecosystem: Ecosystem, packageName: string, version?: string) => void;
  onRefresh: () => void;
}

export function WatchlistView({
  watchlist,
  onTriggerScan,
  onRefresh,
}: WatchlistViewProps) {
  const [newEcosystem, setNewEcosystem] = useState<Ecosystem>("npm");
  const [newPackage, setNewPackage] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [checkMessage, setCheckMessage] = useState<string | null>(null);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const pkg = newPackage.trim();
    if (!pkg) {
      setError("Package name cannot be empty.");
      return;
    }
    setError(null);
    try {
      await addWatchlistItem({
        ecosystem: newEcosystem,
        package_name: pkg,
        notes: notes.trim() || undefined,
      });
      setNewPackage("");
      setNotes("");
      onRefresh();
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleRemove(id: string) {
    try {
      await removeWatchlistItem(id);
      onRefresh();
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleCheckUpdates() {
    setIsChecking(true);
    setCheckMessage(null);
    try {
      const res = await checkWatchlistUpdates();
      setCheckMessage(
        `Checked ${res.checked_count} packages: ${res.updates_detected} update(s) detected, ${res.scans_triggered} scan(s) triggered.`
      );
      onRefresh();
    } catch (err) {
      setCheckMessage(`Check failed: ${String(err)}`);
    } finally {
      setIsChecking(false);
    }
  }

  return (
    <div className="w-full max-w-5xl mx-auto my-6 p-6 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-6 font-mono text-xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2.5">
          <Bookmark className="w-5 h-5 text-amber-400" />
          <h2 className="text-base font-bold text-slate-100">Package Watchlist &amp; Release Monitor</h2>
          <span className="text-slate-500">({watchlist.length} monitored)</span>
        </div>

        <button
          onClick={handleCheckUpdates}
          disabled={isChecking || watchlist.length === 0}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600/20 hover:bg-sky-600/30 border border-sky-500/40 text-sky-300 text-xs font-semibold transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isChecking ? "animate-spin" : ""}`} />
          <span>{isChecking ? "Checking Registries..." : "Check for Updates"}</span>
        </button>
      </div>

      {checkMessage && (
        <div className="p-3 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-sky-400 shrink-0" />
          <span>{checkMessage}</span>
        </div>
      )}

      {/* Add New Package Form */}
      <form onSubmit={handleAdd} className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
        <h3 className="text-xs uppercase text-slate-400 font-semibold tracking-wider flex items-center gap-1.5">
          <BookmarkPlus className="w-4 h-4 text-emerald-400" />
          <span>Monitor New Package</span>
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-2.5">
          <div>
            <select
              value={newEcosystem}
              onChange={(e) => setNewEcosystem(e.target.value as Ecosystem)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs focus:outline-none focus:border-amber-500"
            >
              <option value="npm">npm</option>
              <option value="pypi">PyPI</option>
            </select>
          </div>

          <div className="sm:col-span-2">
            <input
              type="text"
              value={newPackage}
              onChange={(e) => setNewPackage(e.target.value)}
              placeholder="Package name (e.g. lodash, requests)"
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs placeholder-slate-500 focus:outline-none focus:border-amber-500"
              required
            />
          </div>

          <div>
            <button
              type="submit"
              className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-medium transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>Add Watch</span>
            </button>
          </div>
        </div>

        {error && <p className="text-rose-400 text-[11px]">{error}</p>}
      </form>

      {/* Watchlist Table */}
      {watchlist.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 text-[11px] uppercase">
                <th className="py-2.5 px-3 font-semibold">Package</th>
                <th className="py-2.5 px-3 font-semibold">Ecosystem</th>
                <th className="py-2.5 px-3 font-semibold">Last Scanned</th>
                <th className="py-2.5 px-3 font-semibold">Latest Release</th>
                <th className="py-2.5 px-3 font-semibold">Risk Level</th>
                <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {watchlist.map((item) => (
                <tr key={item.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3 px-3">
                    <div className="font-bold text-slate-200">{item.package_name}</div>
                    {item.notes && <div className="text-[10px] text-slate-500 truncate max-w-xs">{item.notes}</div>}
                  </td>
                  <td className="py-3 px-3">
                    <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700 uppercase">
                      {item.ecosystem}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-slate-400 text-[11px]">
                    {item.last_scanned_version ? (
                      <span>v{item.last_scanned_version}</span>
                    ) : (
                      <span className="text-slate-600">Not scanned</span>
                    )}
                  </td>
                  <td className="py-3 px-3 text-[11px]">
                    {item.has_update ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                        <AlertTriangle className="w-3 h-3 text-amber-400" />
                        v{item.latest_version} (Update)
                      </span>
                    ) : item.latest_version ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                        v{item.latest_version} (Latest)
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="py-3 px-3">
                    {item.last_risk_score !== undefined && item.last_risk_score !== null ? (
                      <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700">
                        {item.last_risk_score}/100 ({String(item.last_risk_level || "UNKNOWN")})
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="py-3 px-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() =>
                          onTriggerScan(
                            item.ecosystem,
                            item.package_name,
                            item.has_update ? (item.latest_version ?? undefined) : (item.last_scanned_version ?? undefined)
                          )
                        }
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-emerald-400 text-[11px] transition-colors"
                        title="Scan package now"
                      >
                        <Search className="w-3.5 h-3.5" />
                        <span>Scan</span>
                      </button>
                      <button
                        onClick={() => handleRemove(item.id)}
                        className="p-1 rounded text-slate-500 hover:text-rose-400 transition-colors"
                        title="Remove from watchlist"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="p-12 text-center text-slate-500 space-y-2">
          <Bookmark className="w-8 h-8 mx-auto text-slate-600" />
          <h3 className="text-slate-300 font-bold text-sm">Watchlist is Empty</h3>
          <p className="text-xs text-slate-400 max-w-sm mx-auto">
            Add critical upstream dependencies to monitor new releases, highlight differences, and trigger automated scans.
          </p>
        </div>
      )}
    </div>
  );
}
