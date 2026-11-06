"use client";

import React, { useState } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Activity,
  Layers,
  ArrowRight,
  ScanLine,
  AlertTriangle,
  Bookmark,
  Clock,
  ExternalLink,
  Zap,
} from "lucide-react";
import { Ecosystem, ScanHistoryItem, WatchlistItem } from "../lib/types";

interface OverviewDashboardProps {
  history: ScanHistoryItem[];
  watchlist: WatchlistItem[];
  onStartScan: (ecosystem: Ecosystem, packageName: string, version: string) => void;
  onOpenReport: (item: ScanHistoryItem) => void;
  onNavigateToScanner: () => void;
  onNavigateToWatchlist: () => void;
}

export function OverviewDashboard({
  history,
  watchlist,
  onStartScan,
  onOpenReport,
  onNavigateToScanner,
  onNavigateToWatchlist,
}: OverviewDashboardProps) {
  // Quick scan panel input state
  const [quickEcosystem, setQuickEcosystem] = useState<Ecosystem>("npm");
  const [quickPackage, setQuickPackage] = useState("");
  const [quickVersion, setQuickVersion] = useState("");
  const [quickError, setQuickError] = useState<string | null>(null);

  // Compute live statistics without fabrication
  const totalScans = history.length;
  const uniquePackages = new Set(history.map((h) => `${h.ecosystem}:${h.package_name}`)).size;
  const criticalOrHighScans = history.filter(
    (h) => h.risk_level === "CRITICAL" || h.risk_level === "HIGH"
  ).length;
  const monitoredCount = watchlist.length;

  // Risk distribution breakdown
  const riskCounts = {
    CRITICAL: history.filter((h) => h.risk_level === "CRITICAL").length,
    HIGH: history.filter((h) => h.risk_level === "HIGH").length,
    MEDIUM: history.filter((h) => h.risk_level === "MEDIUM").length,
    LOW: history.filter((h) => h.risk_level === "LOW").length,
  };

  const handleQuickScanSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickPackage.trim()) {
      setQuickError("Package name is required.");
      return;
    }
    if (!quickVersion.trim()) {
      setQuickError("Exact version is required.");
      return;
    }
    setQuickError(null);
    onStartScan(quickEcosystem, quickPackage.trim(), quickVersion.trim());
  };

  const samplePackages: { ecosystem: Ecosystem; name: string; version: string; tag: string }[] = [
    {
      ecosystem: "npm",
      name: "left-pad",
      version: "1.3.0",
      tag: "Authentic & Clean",
    },
    {
      ecosystem: "npm",
      name: "chalk",
      version: "5.3.0",
      tag: "ESM Bundled",
    },
    {
      ecosystem: "npm",
      name: "express",
      version: "4.19.2",
      tag: "Popular Library",
    },
    {
      ecosystem: "npm",
      name: "event-stream",
      version: "3.3.6",
      tag: "Supply Chain Incident",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Threat Intel Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Scans */}
        <div className="p-4 rounded-lg bg-surface-850 border border-surface-border flex items-start justify-between">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
              Total Package Scans
            </span>
            <div className="mt-1 text-2xl font-bold font-mono text-white">
              {totalScans}
            </div>
            <span className="text-xs text-slate-400 mt-0.5 block">
              Audited in local workspace
            </span>
          </div>
          <div className="p-2 rounded bg-surface-800 border border-surface-700 text-violet-400">
            <ScanLine className="w-5 h-5" />
          </div>
        </div>

        {/* Card 2: Packages Analyzed */}
        <div className="p-4 rounded-lg bg-surface-850 border border-surface-border flex items-start justify-between">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
              Unique Dependencies
            </span>
            <div className="mt-1 text-2xl font-bold font-mono text-white">
              {uniquePackages}
            </div>
            <span className="text-xs text-slate-400 mt-0.5 block">
              npm & PyPI registries
            </span>
          </div>
          <div className="p-2 rounded bg-surface-800 border border-surface-700 text-lavender-400">
            <Layers className="w-5 h-5" />
          </div>
        </div>

        {/* Card 3: High / Critical Alerts */}
        <div className="p-4 rounded-lg bg-surface-850 border border-surface-border flex items-start justify-between">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
              Critical / High Alerts
            </span>
            <div
              className={`mt-1 text-2xl font-bold font-mono ${
                criticalOrHighScans > 0 ? "text-soc-critical" : "text-slate-300"
              }`}
            >
              {criticalOrHighScans}
            </div>
            <span className="text-xs text-slate-400 mt-0.5 block">
              Flagged supply-chain risks
            </span>
          </div>
          <div
            className={`p-2 rounded border ${
              criticalOrHighScans > 0
                ? "bg-soc-critical-bg border-soc-critical-border text-soc-critical"
                : "bg-surface-800 border-surface-700 text-slate-400"
            }`}
          >
            <ShieldAlert className="w-5 h-5" />
          </div>
        </div>

        {/* Card 4: Packages Monitored */}
        <div
          onClick={onNavigateToWatchlist}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              onNavigateToWatchlist();
            }
          }}
          className="p-4 rounded-lg bg-surface-850 border border-surface-border flex items-start justify-between cursor-pointer hover:border-violet-600/40 transition-colors"
        >
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
              Watchlist Monitored
            </span>
            <div className="mt-1 text-2xl font-bold font-mono text-white">
              {monitoredCount}
            </div>
            <span className="text-xs text-slate-400 mt-0.5 block">
              Tracked for new releases
            </span>
          </div>
          <div className="p-2 rounded bg-surface-800 border border-surface-700 text-violet-400">
            <Bookmark className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Main Grid: Quick Scan & Risk Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Quick Scan Panel */}
        <div className="lg:col-span-2 p-5 rounded-lg bg-surface-850 border border-surface-border space-y-4">
          <div className="flex items-center justify-between border-b border-surface-border pb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 rounded bg-violet-950/60 border border-violet-800 text-violet-400">
                <Zap className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">
                  Quick Package Verification
                </h3>
                <p className="text-xs text-slate-400">
                  Analyze tarball against published repository commit with zero code execution
                </p>
              </div>
            </div>
            <button
              onClick={onNavigateToScanner}
              className="text-xs font-mono text-violet-400 hover:text-violet-300 flex items-center gap-1"
            >
              <span>Advanced Scanner</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <form onSubmit={handleQuickScanSubmit} className="space-y-3.5">
            {quickError && (
              <div className="p-2.5 rounded bg-soc-critical-bg border border-soc-critical-border text-xs text-rose-300 font-mono">
                {quickError}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
              {/* Ecosystem Selector */}
              <div className="sm:col-span-3">
                <label className="block text-[11px] font-mono text-slate-400 mb-1 uppercase">
                  Ecosystem
                </label>
                <div className="grid grid-cols-2 rounded-md bg-surface-800 p-0.5 border border-surface-border">
                  <button
                    type="button"
                    onClick={() => setQuickEcosystem("npm")}
                    className={`py-1.5 text-xs font-mono rounded transition-colors ${
                      quickEcosystem === "npm"
                        ? "bg-violet-600 text-white font-bold"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    npm
                  </button>
                  <button
                    type="button"
                    onClick={() => setQuickEcosystem("pypi")}
                    className={`py-1.5 text-xs font-mono rounded transition-colors ${
                      quickEcosystem === "pypi"
                        ? "bg-violet-600 text-white font-bold"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    PyPI
                  </button>
                </div>
              </div>

              {/* Package Name Input */}
              <div className="sm:col-span-5">
                <label className="block text-[11px] font-mono text-slate-400 mb-1 uppercase">
                  Package Name
                </label>
                <input
                  type="text"
                  value={quickPackage}
                  onChange={(e) => setQuickPackage(e.target.value)}
                  placeholder={quickEcosystem === "npm" ? "e.g. left-pad, express" : "e.g. requests, urllib3"}
                  className="w-full px-3 py-1.5 text-xs font-mono bg-surface-800 border border-surface-border rounded-md text-white placeholder-slate-400 focus:outline-none focus:border-violet-500"
                />
              </div>

              {/* Version Input */}
              <div className="sm:col-span-2">
                <label className="block text-[11px] font-mono text-slate-400 mb-1 uppercase">
                  Version
                </label>
                <input
                  type="text"
                  value={quickVersion}
                  onChange={(e) => setQuickVersion(e.target.value)}
                  placeholder={quickEcosystem === "npm" ? "1.3.0" : "2.31.0"}
                  className="w-full px-3 py-1.5 text-xs font-mono bg-surface-800 border border-surface-border rounded-md text-white placeholder-slate-400 focus:outline-none focus:border-violet-500"
                />
              </div>

              {/* Submit Button */}
              <div className="sm:col-span-2">
                <button
                  type="submit"
                  className="w-full py-2 px-3 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold font-mono flex items-center justify-center gap-1.5 transition-all shadow-glow-sm"
                >
                  <ScanLine className="w-3.5 h-3.5" />
                  <span>Verify</span>
                </button>
              </div>
            </div>
          </form>

          {/* Quick Sample Selector */}
          <div className="pt-2">
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider block mb-2">
              Verified Supply-Chain Scenarios:
            </span>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {samplePackages.map((s) => (
                <button
                  key={`${s.ecosystem}-${s.name}`}
                  type="button"
                  onClick={() => {
                    setQuickEcosystem(s.ecosystem);
                    setQuickPackage(s.name);
                    setQuickVersion(s.version);
                    onStartScan(s.ecosystem, s.name, s.version);
                  }}
                  className="p-2 rounded bg-surface-800 hover:bg-surface-750 border border-surface-border hover:border-violet-600/40 text-left transition-all group"
                >
                  <div className="flex items-center justify-between text-xs font-mono text-slate-200 group-hover:text-violet-300">
                    <span className="font-semibold truncate">{s.name}</span>
                    <span className="text-[10px] text-slate-400">@{s.version}</span>
                  </div>
                  <span className="text-[10px] text-slate-400 truncate block mt-0.5">
                    {s.tag}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right 1 Col: Risk Distribution & Posture */}
        <div className="p-5 rounded-lg bg-surface-850 border border-surface-border flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between border-b border-surface-border pb-3">
              <h3 className="text-sm font-semibold text-white">Risk Distribution</h3>
              <span className="text-[10px] font-mono text-slate-400">
                {totalScans} evaluated
              </span>
            </div>

            <div className="space-y-3 mt-4 text-xs font-mono">
              {/* Critical */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-slate-300">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-soc-critical" />
                    <span>Critical Risk</span>
                  </div>
                  <span className="font-bold text-soc-critical">{riskCounts.CRITICAL}</span>
                </div>
                <div className="h-1.5 w-full bg-surface-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-soc-critical transition-all"
                    style={{
                      width: totalScans ? `${(riskCounts.CRITICAL / totalScans) * 100}%` : "0%",
                    }}
                  />
                </div>
              </div>

              {/* High */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-slate-300">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-soc-high" />
                    <span>High Risk</span>
                  </div>
                  <span className="font-bold text-soc-high">{riskCounts.HIGH}</span>
                </div>
                <div className="h-1.5 w-full bg-surface-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-soc-high transition-all"
                    style={{
                      width: totalScans ? `${(riskCounts.HIGH / totalScans) * 100}%` : "0%",
                    }}
                  />
                </div>
              </div>

              {/* Medium */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-slate-300">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-soc-medium" />
                    <span>Medium Risk</span>
                  </div>
                  <span className="font-bold text-soc-medium">{riskCounts.MEDIUM}</span>
                </div>
                <div className="h-1.5 w-full bg-surface-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-soc-medium transition-all"
                    style={{
                      width: totalScans ? `${(riskCounts.MEDIUM / totalScans) * 100}%` : "0%",
                    }}
                  />
                </div>
              </div>

              {/* Low / Clean */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-slate-300">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-soc-verified" />
                    <span>Low / Clean</span>
                  </div>
                  <span className="font-bold text-soc-verified">{riskCounts.LOW}</span>
                </div>
                <div className="h-1.5 w-full bg-surface-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-soc-verified transition-all"
                    style={{
                      width: totalScans ? `${(riskCounts.LOW / totalScans) * 100}%` : "0%",
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="p-3 rounded bg-surface-800 border border-surface-border text-[11px] text-slate-400 font-mono space-y-1">
            <div className="flex items-center gap-2 text-violet-300 font-semibold">
              <ShieldCheck className="w-4 h-4 text-violet-400" />
              <span>Deterministic Scoring</span>
            </div>
            <p>
              Risk is evaluated 0–100 via verifiable source differences, AST static analysis, and Sigstore cryptographic provenance.
            </p>
          </div>
        </div>
      </div>

      {/* Bottom Section: Recent Scan Activity */}
      <div className="p-5 rounded-lg bg-surface-850 border border-surface-border space-y-4">
        <div className="flex items-center justify-between border-b border-surface-border pb-3">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" />
            <h3 className="text-sm font-semibold text-white">Recent Scan Activity</h3>
          </div>
          {history.length > 0 && (
            <span className="text-xs font-mono text-slate-400">
              Showing last {Math.min(history.length, 10)} scans
            </span>
          )}
        </div>

        {history.length === 0 ? (
          <div className="py-12 text-center space-y-3">
            <div className="w-12 h-12 mx-auto rounded-full bg-surface-800 border border-surface-700 flex items-center justify-center text-slate-400">
              <Activity className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-200">
                No Security Scans Recorded Yet
              </p>
              <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
                Scan an npm or PyPI package to analyze uncommitted code changes, static security findings, and cryptographic provenance.
              </p>
            </div>
            <button
              onClick={onNavigateToScanner}
              className="mt-2 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-xs font-mono font-medium transition-all shadow-glow-sm"
            >
              <ScanLine className="w-3.5 h-3.5" />
              <span>Launch First Scan</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-surface-border text-slate-400 text-[11px] uppercase tracking-wider">
                  <th className="pb-2 font-medium">Package</th>
                  <th className="pb-2 font-medium">Version</th>
                  <th className="pb-2 font-medium">Ecosystem</th>
                  <th className="pb-2 font-medium">Risk Score</th>
                  <th className="pb-2 font-medium">Timestamp</th>
                  <th className="pb-2 font-medium text-right">Investigation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {history.slice(0, 10).map((item) => {
                  const isHighOrCritical =
                    item.risk_level === "CRITICAL" || item.risk_level === "HIGH";
                  return (
                    <tr
                      key={item.scan_id}
                      className="hover:bg-surface-800/60 transition-colors group"
                    >
                      <td className="py-2.5 font-bold text-white flex items-center gap-2">
                        {isHighOrCritical ? (
                          <AlertTriangle className="w-3.5 h-3.5 text-soc-critical shrink-0" />
                        ) : (
                          <ShieldCheck className="w-3.5 h-3.5 text-soc-verified shrink-0" />
                        )}
                        <span className="truncate max-w-[200px]">{item.package_name}</span>
                      </td>
                      <td className="py-2.5 text-slate-300">{item.version}</td>
                      <td className="py-2.5">
                        <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold bg-surface-800 text-slate-300 border border-surface-700">
                          {item.ecosystem}
                        </span>
                      </td>
                      <td className="py-2.5">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            item.risk_level === "CRITICAL"
                              ? "bg-soc-critical-bg text-soc-critical border-soc-critical-border"
                              : item.risk_level === "HIGH"
                                ? "bg-soc-high-bg text-soc-high border-soc-high-border"
                                : item.risk_level === "MEDIUM"
                                  ? "bg-soc-medium-bg text-soc-medium border-soc-medium-border"
                                  : "bg-soc-verified-bg text-soc-verified border-soc-verified-border"
                          }`}
                        >
                          {item.risk_score !== undefined
                            ? `${item.risk_level} (${item.risk_score}/100)`
                            : item.risk_level || "UNKNOWN"}
                        </span>
                      </td>
                      <td className="py-2.5 text-slate-400 text-[11px]">
                        {new Date(item.timestamp).toLocaleString(undefined, {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td className="py-2.5 text-right">
                        <button
                          onClick={() => onOpenReport(item)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-surface-800 hover:bg-violet-600 hover:text-white text-slate-300 text-[11px] font-medium transition-all"
                        >
                          <span>Inspect</span>
                          <ExternalLink className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
