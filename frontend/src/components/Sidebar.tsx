"use client";

import React from "react";
import {
  LayoutDashboard,
  ScanLine,
  FileSearch,
  History,
  Bookmark,
  Settings as SettingsIcon,
  Shield,
  Terminal,
  Cpu,
  Database,
} from "lucide-react";

export type NavTab = "overview" | "scanner" | "report" | "history" | "watchlist" | "settings";

interface SidebarProps {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  hasActiveReport: boolean;
  historyCount: number;
  watchlistCount: number;
  backendOnline: boolean | null;
  ollamaOnline: boolean | null;
  onOpenQuickScan?: () => void;
}

export function Sidebar({
  activeTab,
  setActiveTab,
  hasActiveReport,
  historyCount,
  watchlistCount,
  backendOnline,
  ollamaOnline,
}: SidebarProps) {
  const navItems = [
    {
      id: "overview" as const,
      label: "Overview",
      badge: null,
      icon: LayoutDashboard,
      description: "Threat telemetry & stats",
    },
    {
      id: "scanner" as const,
      label: "Package Scanner",
      badge: null,
      icon: ScanLine,
      description: "npm & PyPI verification",
    },
    ...(hasActiveReport
      ? [
          {
            id: "report" as const,
            label: "Investigation",
            badge: "ACTIVE",
            badgeColor: "bg-violet-900/50 text-violet-300 border-violet-700/60",
            icon: FileSearch,
            description: "Active report & AST findings",
          },
        ]
      : []),
    {
      id: "history" as const,
      label: "Scan History",
      badge: historyCount > 0 ? String(historyCount) : null,
      badgeColor: "bg-surface-800 text-slate-300 border-surface-700",
      icon: History,
      description: "Audit trail & past reports",
    },
    {
      id: "watchlist" as const,
      label: "Watchlist",
      badge: watchlistCount > 0 ? String(watchlistCount) : null,
      badgeColor: "bg-surface-800 text-slate-300 border-surface-700",
      icon: Bookmark,
      description: "Continuous release monitoring",
    },
    {
      id: "settings" as const,
      label: "Settings",
      badge: null,
      icon: SettingsIcon,
      description: "Engine endpoints & telemetry",
    },
  ];

  return (
    <aside className="w-64 shrink-0 bg-surface-900 border-r border-surface-border flex flex-col justify-between select-none">
      {/* Top Branding Section */}
      <div>
        <div className="h-16 px-4 flex items-center justify-between border-b border-surface-border">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-md bg-gradient-to-br from-violet-600 to-violet-900 border border-violet-500/30 flex items-center justify-center shadow-glow-sm">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-base tracking-wider text-white font-mono">
                  VERITOR
                </span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-surface-800 text-violet-400 font-mono border border-surface-700">
                  SOC
                </span>
              </div>
              <p className="text-[10px] text-slate-400 font-mono tracking-tight">
                Supply-Chain Security
              </p>
            </div>
          </div>
        </div>

        {/* Engine Mission Statement Pill */}
        <div className="mx-3 mt-3 px-2.5 py-1.5 rounded bg-surface-850/80 border border-surface-border flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-violet-400 shrink-0" />
          <span className="text-[11px] font-mono text-slate-300 truncate">
            Verify Before You Trust.
          </span>
        </div>

        {/* Navigation Section */}
        <div className="px-2 py-4 space-y-1">
          <div className="px-2 pb-1.5 text-[10px] font-mono uppercase tracking-wider text-slate-400">
            Console Navigation
          </div>
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all group ${
                  isActive
                    ? "bg-violet-950/60 text-white border-l-2 border-violet-500 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-surface-850/80"
                }`}
              >
                <div className="flex items-center gap-2.5 truncate">
                  <Icon
                    className={`w-4 h-4 shrink-0 transition-colors ${
                      isActive
                        ? "text-violet-400"
                        : "text-slate-400 group-hover:text-slate-300"
                    }`}
                  />
                  <div className="text-left truncate">
                    <div className="truncate font-sans font-medium text-[13px]">{item.label}</div>
                  </div>
                </div>

                {item.badge && (
                  <span
                    className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                      item.badgeColor || "bg-surface-800 text-slate-300 border-surface-700"
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Bottom Telemetry & Status Section */}
      <div className="p-3 border-t border-surface-border bg-surface-950/60 space-y-2.5">
        <div className="px-1 flex items-center justify-between text-[11px] font-mono text-slate-400">
          <span>SYSTEM TELEMETRY</span>
          <span className="text-[10px] text-slate-400">v0.1.0</span>
        </div>

        {/* Live Service Status Indicators */}
        <div className="space-y-1.5 text-xs font-mono">
          <div className="flex items-center justify-between px-2 py-1 rounded bg-surface-850 border border-surface-border">
            <div className="flex items-center gap-2 text-slate-400">
              <Database className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-[11px]">Backend API</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  backendOnline === true
                    ? "bg-emerald-400"
                    : backendOnline === false
                      ? "bg-rose-500"
                      : "bg-amber-400 animate-pulse"
                }`}
              />
              <span
                className={`text-[10px] font-semibold ${
                  backendOnline === true
                    ? "text-emerald-400"
                    : backendOnline === false
                      ? "text-rose-400"
                      : "text-amber-400"
                }`}
              >
                {backendOnline === true ? "ONLINE" : backendOnline === false ? "OFFLINE" : "PING"}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between px-2 py-1 rounded bg-surface-850 border border-surface-border">
            <div className="flex items-center gap-2 text-slate-400">
              <Cpu className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-[11px]">Ollama AI</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  ollamaOnline === true
                    ? "bg-violet-400"
                    : ollamaOnline === false
                      ? "bg-slate-500"
                      : "bg-amber-400 animate-pulse"
                }`}
              />
              <span
                className={`text-[10px] font-semibold ${
                  ollamaOnline === true
                    ? "text-violet-300"
                    : ollamaOnline === false
                      ? "text-slate-400"
                      : "text-amber-400"
                }`}
              >
                {ollamaOnline === true ? "ACTIVE" : ollamaOnline === false ? "STANDBY" : "PING"}
              </span>
            </div>
          </div>
        </div>

        {/* Security Assurance Badge */}
        <div className="pt-1 flex items-center justify-between text-[10px] text-slate-400 font-mono">
          <span className="truncate">Deterministic Security Engine</span>
          <span className="text-violet-400 shrink-0">Zero-Exec</span>
        </div>
      </div>
    </aside>
  );
}
