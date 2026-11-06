"use client";

import React from "react";
import {
  CheckCircle2,
  CircleDashed,
  AlertOctagon,
  Clock,
  Sparkles,
  GitCompare,
  ShieldAlert,
  Lock,
  Layers,
  RotateCw,
  Terminal,
} from "lucide-react";
import { ScanStage, ScanStatusResponse } from "../lib/types";

interface ProgressTrackerProps {
  status: ScanStatusResponse;
  onRetry?: () => void;
}

const STAGES_ORDER: { key: ScanStage; label: string; icon: React.ElementType }[] = [
  { key: "fetching_metadata", label: "Registry Metadata", icon: Clock },
  { key: "downloading_artifact", label: "Download Tarball", icon: Layers },
  { key: "resolving_source", label: "Resolve Source Git", icon: GitCompare },
  { key: "extracting_package", label: "Extract Package", icon: Layers },
  { key: "downloading_source", label: "Fetch Git Tree", icon: GitCompare },
  { key: "comparing", label: "Differential Engine", icon: GitCompare },
  { key: "security_scanning", label: "AST Security Walk", icon: ShieldAlert },
  { key: "checking_provenance", label: "Sigstore Provenance", icon: Lock },
  { key: "scoring_risk", label: "Deterministic Scoring", icon: Layers },
  { key: "ai_investigation", label: "AI Reasoning", icon: Sparkles },
  { key: "completed", label: "Integrity Verified", icon: CheckCircle2 },
];

export function ProgressTracker({ status, onRetry }: ProgressTrackerProps) {
  const currentStageIndex = STAGES_ORDER.findIndex((s) => s.key === status.stage);
  const isFailed = status.status === "failed";
  const isCompleted = status.status === "completed";

  return (
    <div className="w-full max-w-3xl mx-auto my-6 p-6 rounded-xl bg-surface-850 border border-surface-border shadow-2xl space-y-6">
      {/* Header telemetry */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-surface-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] uppercase font-mono px-2 py-0.5 rounded bg-violet-950/60 text-violet-300 border border-violet-800">
              {status.ecosystem}
            </span>
            <span className="text-base sm:text-lg font-mono font-bold text-white">
              {status.package_name}@{status.version}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 font-mono flex items-center gap-1.5">
            <Terminal className="w-3.5 h-3.5 text-slate-500" />
            <span>Scan ID:</span>
            <span className="text-slate-300">{status.scan_id}</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          {isFailed ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-soc-critical-bg border border-soc-critical-border text-soc-critical text-xs font-mono font-medium">
              <AlertOctagon className="w-4 h-4 text-soc-critical" />
              FAILED
            </span>
          ) : isCompleted ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-emerald-950/40 border border-emerald-700/50 text-emerald-300 text-xs font-mono font-medium">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              COMPLETED
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-violet-950/50 border border-violet-700/50 text-violet-300 text-xs font-mono font-medium animate-pulse">
              <CircleDashed className="w-4 h-4 text-violet-400 animate-spin" />
              ANALYZING
            </span>
          )}
        </div>
      </div>

      {/* Progress Bar & Current Activity */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-slate-300 truncate max-w-[80%]">
            {status.message || "Running verification pipeline stages..."}
          </span>
          <span className="text-violet-400 font-semibold">{status.progress_percent}%</span>
        </div>
        <div className="w-full h-2 rounded-full bg-surface-950 overflow-hidden border border-surface-border">
          <div
            className={`h-full transition-all duration-300 ease-out rounded-full ${
              isFailed
                ? "bg-soc-critical"
                : isCompleted
                ? "bg-emerald-500"
                : "bg-gradient-to-r from-violet-600 via-violet-500 to-lavender-400"
            }`}
            style={{ width: `${Math.max(5, Math.min(100, status.progress_percent))}%` }}
          />
        </div>
      </div>

      {/* Error Banner if Failed */}
      {isFailed && (
        <div className="p-4 rounded-lg bg-soc-critical-bg border border-soc-critical-border text-rose-200 text-xs font-mono space-y-2">
          <div className="flex items-center gap-2 font-bold text-soc-critical">
            <AlertOctagon className="w-4 h-4" />
            <span>Analysis Interrupted</span>
          </div>
          <p className="text-slate-300 leading-relaxed">
            {status.error || "The scan encountered an unexpected pipeline execution error."}
          </p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-800 hover:bg-surface-750 border border-soc-critical-border text-rose-200 font-mono text-xs transition-colors"
            >
              <RotateCw className="w-3.5 h-3.5" />
              <span>Retry Scan</span>
            </button>
          )}
        </div>
      )}

      {/* Pipeline Stage Steps */}
      <div className="pt-2">
        <h4 className="text-xs uppercase tracking-wider font-mono text-slate-400 mb-3 font-semibold">
          Verification Pipeline Stages
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 text-xs font-mono">
          {STAGES_ORDER.map((stage, idx) => {
            const Icon = stage.icon;
            const isStageComplete = isCompleted || currentStageIndex > idx;
            const isStageCurrent =
              !isCompleted &&
              !isFailed &&
              (currentStageIndex === idx || (currentStageIndex === -1 && idx === 0));

            return (
              <div
                key={stage.key}
                className={`flex items-center gap-2.5 p-2 rounded-lg border transition-all ${
                  isStageComplete
                    ? "bg-surface-900 border-surface-border text-slate-300"
                    : isStageCurrent
                    ? "bg-surface-800 border-violet-500/50 text-violet-200 shadow-sm ring-1 ring-violet-500/20"
                    : "bg-surface-950/40 border-surface-900 text-slate-600"
                }`}
              >
                {isStageComplete ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                ) : isStageCurrent ? (
                  <CircleDashed className="w-4 h-4 text-violet-400 animate-spin shrink-0" />
                ) : (
                  <Icon className="w-4 h-4 text-slate-600 shrink-0" />
                )}
                <span className="truncate">{stage.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
