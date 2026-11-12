"use client";

import React from "react";
import {
  ShieldCheck,
  Terminal,
} from "lucide-react";
import { Ecosystem } from "../lib/types";

interface LandingHeroProps {
  onSelectSample: (ecosystem: Ecosystem, name: string, version: string) => void;
}

export function LandingHero({ onSelectSample }: LandingHeroProps) {
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
      tag: "Historical Supply Chain Incident",
    },
  ];

  return (
    <div className="p-5 rounded-lg bg-surface-850 border border-surface-border">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded bg-violet-950/60 border border-violet-800/60 text-[11px] font-mono text-violet-300">
            <ShieldCheck className="w-3.5 h-3.5 text-violet-400" />
            <span>Autonomous Supply Chain Verification Engine</span>
          </div>
          <h2 className="text-lg font-bold text-white tracking-tight">
            Verify Published Packages Against Authoritative Source Repositories
          </h2>
          <p className="text-xs text-slate-400 max-w-2xl">
            Detect discrepancies, injected build artifacts, uncommitted lifecycle scripts, and malicious obfuscated signals before installing third-party dependencies.
          </p>
        </div>

        {/* Quick Sample Trigger Pill */}
        <div className="shrink-0 flex items-center gap-2 text-xs font-mono text-slate-400">
          <Terminal className="w-4 h-4 text-violet-400" />
          <span>Select Scenario:</span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 pt-3 border-t border-surface-border">
        {samplePackages.map((pkg) => (
          <button
            key={`${pkg.ecosystem}-${pkg.name}`}
            type="button"
            onClick={() => onSelectSample(pkg.ecosystem, pkg.name, pkg.version)}
            className="p-2.5 rounded bg-surface-800 hover:bg-surface-750 border border-surface-border hover:border-violet-600/50 text-left transition-all group"
          >
            <div className="flex items-center justify-between text-xs font-mono text-slate-200 group-hover:text-violet-300">
              <span className="font-semibold">{pkg.name}</span>
              <span className="text-[10px] text-slate-400">@{pkg.version}</span>
            </div>
            <span className="text-[10px] text-slate-400 block mt-0.5 truncate">
              {pkg.tag}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
