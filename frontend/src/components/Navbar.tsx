"use client";

import React, { useEffect, useState } from "react";
import {
  LayoutDashboard,
  ScanLine,
  FileSearch,
  History,
  Bookmark,
  Settings as SettingsIcon,
  Shield,
  Database,
  Cpu,
} from "lucide-react";
import { checkBackendHealth, checkOllamaConnection } from "../lib/api";

interface NavbarProps {
  activeTab: "overview" | "scanner" | "report" | "history" | "watchlist" | "settings" | string;
  setActiveTab: (tab: "overview" | "scanner" | "report" | "history" | "watchlist" | "settings" | string) => void;
  hasActiveReport: boolean;
  historyCount: number;
  watchlistCount: number;
}

export function Navbar({
  activeTab,
  setActiveTab,
  hasActiveReport,
  historyCount,
  watchlistCount,
}: NavbarProps) {
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [ollamaOnline, setOllamaOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;

    async function checkStatus() {
      try {
        const backend = await checkBackendHealth();
        if (mounted) {
          setBackendOnline(backend.status === "ok");
        }
      } catch {
        if (mounted) setBackendOnline(false);
      }

      try {
        const ollama = await checkOllamaConnection();
        if (mounted) {
          setOllamaOnline(ollama.connected);
        }
      } catch {
        if (mounted) setOllamaOnline(false);
      }
    }

    checkStatus();
    const interval = setInterval(checkStatus, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="bg-surface-900 border-b border-surface-border sticky top-0 z-40 select-none">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          {/* Logo & Brand */}
          <div
            className="flex items-center gap-3 cursor-pointer"
            onClick={() => setActiveTab("overview")}
          >
            <div className="w-8 h-8 rounded-md bg-gradient-to-br from-violet-600 to-violet-900 border border-violet-500/30 flex items-center justify-center shadow-glow-sm">
              <Shield className="w-4 h-4 text-white" />
            </div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm tracking-wider text-white font-mono">
                VERITOR
              </span>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-surface-800 text-violet-400 font-mono border border-surface-700">
                SOC
              </span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab("overview")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono transition-colors ${
                activeTab === "overview"
                  ? "bg-violet-950/60 text-white border border-violet-700/60"
                  : "text-slate-400 hover:text-white hover:bg-surface-800"
              }`}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              <span>Overview</span>
            </button>

            <button
              onClick={() => setActiveTab("scanner")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono transition-colors ${
                activeTab === "scanner"
                  ? "bg-violet-950/60 text-white border border-violet-700/60"
                  : "text-slate-400 hover:text-white hover:bg-surface-800"
              }`}
            >
              <ScanLine className="w-3.5 h-3.5" />
              <span>Scanner</span>
            </button>

            {hasActiveReport && (
              <button
                onClick={() => setActiveTab("report")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono transition-colors ${
                  activeTab === "report"
                    ? "bg-violet-950/60 text-white border border-violet-700/60"
                    : "text-slate-400 hover:text-white hover:bg-surface-800"
                }`}
              >
                <FileSearch className="w-3.5 h-3.5 text-violet-400" />
                <span>Report</span>
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
              </button>
            )}

            <button
              onClick={() => setActiveTab("history")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono transition-colors ${
                activeTab === "history"
                  ? "bg-violet-950/60 text-white border border-violet-700/60"
                  : "text-slate-400 hover:text-white hover:bg-surface-800"
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">History</span>
              {historyCount > 0 && (
                <span className="text-[10px] px-1 rounded bg-surface-800 text-slate-300 border border-surface-700">
                  {historyCount}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("watchlist")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono transition-colors ${
                activeTab === "watchlist"
                  ? "bg-violet-950/60 text-white border border-violet-700/60"
                  : "text-slate-400 hover:text-white hover:bg-surface-800"
              }`}
            >
              <Bookmark className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Watchlist</span>
              {watchlistCount > 0 && (
                <span className="text-[10px] px-1 rounded bg-surface-800 text-slate-300 border border-surface-700">
                  {watchlistCount}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("settings")}
              className={`p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-surface-800 transition-colors ${
                activeTab === "settings" ? "text-violet-400 bg-surface-800" : ""
              }`}
              title="Settings"
            >
              <SettingsIcon className="w-4 h-4" />
            </button>
          </nav>

          {/* Right Status */}
          <div className="hidden lg:flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-850 border border-surface-border text-[11px] font-mono text-slate-400">
              <Database className="w-3 h-3" />
              <span>API:</span>
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  backendOnline ? "bg-emerald-400" : "bg-rose-500"
                }`}
              />
            </div>
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-850 border border-surface-border text-[11px] font-mono text-slate-400">
              <Cpu className="w-3 h-3" />
              <span>AI:</span>
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  ollamaOnline ? "bg-violet-400" : "bg-slate-500"
                }`}
              />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
