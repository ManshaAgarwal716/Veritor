"use client";

import React from "react";
import {
  Menu,
  Database,
  Cpu,
  Plus,
  ChevronRight,
} from "lucide-react";
import { NavTab } from "./Sidebar";
import { ScanReportResponse } from "../lib/types";

interface TopHeaderProps {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  scanReport: ScanReportResponse | null;
  backendOnline: boolean | null;
  ollamaOnline: boolean | null;
  onToggleMobileMenu?: () => void;
}

export function TopHeader({
  activeTab,
  setActiveTab,
  scanReport,
  backendOnline,
  ollamaOnline,
  onToggleMobileMenu,
}: TopHeaderProps) {
  const getTabLabel = (tab: NavTab): string => {
    switch (tab) {
      case "overview":
        return "Security Overview & Telemetry";
      case "scanner":
        return "Package Integrity Scanner";
      case "report":
        return scanReport
          ? `Investigation — ${scanReport.package_name}@${scanReport.version}`
          : "Investigation Workspace";
      case "history":
        return "Scan Audit History";
      case "watchlist":
        return "Supply Chain Watchlist";
      case "settings":
        return "Engine Configuration";
    }
  };

  return (
    <header className="h-14 bg-surface-900 border-b border-surface-border px-4 lg:px-6 flex items-center justify-between select-none">
      {/* Left: Mobile Toggle + Breadcrumb */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleMobileMenu}
          className="lg:hidden p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-surface-800 transition-colors"
          title="Toggle Navigation Menu"
          aria-label="Toggle Navigation Drawer"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="text-slate-400">Veritor Console</span>
          <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="text-white font-medium">{getTabLabel(activeTab)}</span>
        </div>
      </div>

      {/* Right: Quick Actions & Status Badges */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Quick New Scan Action Button */}
        {activeTab !== "scanner" && (
          <button
            onClick={() => setActiveTab("scanner")}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium transition-all shadow-glow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">New Scan</span>
          </button>
        )}

        {/* Backend Status Pill */}
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface-850 border border-surface-border text-xs font-mono text-slate-300">
          <Database className="w-3 h-3 text-slate-400" />
          <span className="text-[11px] text-slate-400">API:</span>
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
            className={`text-[11px] ${
              backendOnline === true
                ? "text-emerald-400"
                : backendOnline === false
                  ? "text-rose-400"
                  : "text-amber-400"
            }`}
          >
            {backendOnline === true ? "OK" : backendOnline === false ? "DOWN" : "CONNECTING"}
          </span>
        </div>

        {/* Ollama Status Pill */}
        <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface-850 border border-surface-border text-xs font-mono text-slate-300">
          <Cpu className="w-3 h-3 text-slate-400" />
          <span className="text-[11px] text-slate-400">AI:</span>
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
            className={`text-[11px] ${
              ollamaOnline === true
                ? "text-violet-300"
                : ollamaOnline === false
                  ? "text-slate-400"
                  : "text-amber-400"
            }`}
          >
            {ollamaOnline === true ? "READY" : ollamaOnline === false ? "STANDBY" : "PROBING"}
          </span>
        </div>
      </div>
    </header>
  );
}
