"use client";

import React, { useEffect, useState } from "react";
import {
  ShieldCheck,
  Download,
  Clock,
  Layers,
  Sparkles,
  GitBranch,
  CheckCircle2,
  AlertOctagon,
  FileText,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { ReleaseComparisonResponse, RiskLevel, ScanReportResponse } from "../lib/types";
import { compareScanWithPrevious, exportScanJson, exportScanPdf } from "../lib/api";

interface ReportDashboardProps {
  report: ScanReportResponse;
  activeReportTab: "overview" | "files" | "findings" | "provenance" | "ai";
  setActiveReportTab: (tab: "overview" | "files" | "findings" | "provenance" | "ai") => void;
}

export function ReportDashboard({
  report,
  activeReportTab,
  setActiveReportTab,
}: ReportDashboardProps) {
  const risk = report.risk;
  const security = report.security;
  const comparison = report.comparison;
  const provenance = report.provenance;

  const score = risk?.score ?? 0;
  const level: RiskLevel = risk?.level ?? "LOW";

  // Color mappings based on risk level
  const getRiskColor = (lvl: RiskLevel) => {
    switch (lvl) {
      case "CRITICAL":
        return {
          text: "text-soc-critical",
          bg: "bg-soc-critical-bg",
          border: "border-soc-critical-border",
          badge: "bg-rose-500/20 text-rose-300 border-rose-500/40",
          gauge: "#f43f5e",
        };
      case "HIGH":
        return {
          text: "text-soc-high",
          bg: "bg-orange-500/10",
          border: "border-orange-500/30",
          badge: "bg-orange-500/20 text-orange-300 border-orange-500/40",
          gauge: "#f97316",
        };
      case "MEDIUM":
        return {
          text: "text-soc-medium",
          bg: "bg-amber-500/10",
          border: "border-amber-500/30",
          badge: "bg-amber-500/20 text-amber-300 border-amber-500/40",
          gauge: "#f59e0b",
        };
      case "LOW":
      default:
        return {
          text: "text-soc-verified",
          bg: "bg-emerald-500/10",
          border: "border-emerald-500/30",
          badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
          gauge: "#10b981",
        };
    }
  };

  const colors = getRiskColor(level);

  const [exportingJson, setExportingJson] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [comparisonData, setComparisonData] = useState<ReleaseComparisonResponse | null>(null);

  useEffect(() => {
    let active = true;
    async function fetchComparison() {
      try {
        const data = await compareScanWithPrevious(report.scan_id);
        if (active) setComparisonData(data);
      } catch {
        if (active) setComparisonData(null);
      }
    }
    fetchComparison();
    return () => {
      active = false;
    };
  }, [report.scan_id]);

  async function handleExportJson() {
    try {
      setExportingJson(true);
      const data = await exportScanJson(report.scan_id);
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `veritor-report-${report.ecosystem}-${report.package_name}-${report.version}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("Failed to export JSON report: " + String(err));
    } finally {
      setExportingJson(false);
    }
  }

  async function handleExportPdf() {
    try {
      setExportingPdf(true);
      const blob = await exportScanPdf(report.scan_id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `veritor-report-${report.ecosystem}-${report.package_name}-${report.version}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("Failed to export PDF report: " + String(err));
    } finally {
      setExportingPdf(false);
    }
  }

  return (
    <div className="w-full space-y-6">
      {/* Top Banner Card */}
      <div className="p-6 rounded-xl bg-surface-850 border border-surface-border shadow-xl">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-violet-950/60 text-violet-300 border border-violet-800">
                {report.ecosystem}
              </span>
              <h1 className="text-xl sm:text-2xl font-bold font-mono text-white">
                {report.package_name}
              </h1>
              <span className="text-sm sm:text-base font-mono text-slate-400">
                v{report.version}
              </span>
              <span
                className={`text-xs font-mono font-semibold px-2.5 py-0.5 rounded-full border ${colors.badge}`}
              >
                {level} RISK ({score}/100)
              </span>
            </div>

            <p className="text-xs text-slate-400 font-mono flex flex-wrap items-center gap-x-4 gap-y-1 pt-1">
              <span>Scan ID: {report.scan_id}</span>
              {report.duration_seconds !== null && report.duration_seconds !== undefined && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  {report.duration_seconds.toFixed(2)}s analysis
                </span>
              )}
              {report.source_match?.repository_url && (
                <span className="flex items-center gap-1 truncate max-w-xs sm:max-w-md">
                  <GitBranch className="w-3.5 h-3.5 text-violet-400" />
                  <a
                    href={report.source_match.repository_url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-violet-300 underline decoration-surface-700"
                  >
                    {report.source_match.repository_url.replace("https://github.com/", "")}
                  </a>
                </span>
              )}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleExportJson}
              disabled={exportingJson}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-800 hover:bg-surface-750 border border-surface-border text-xs font-mono text-slate-300 transition-colors disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5 text-slate-400" />
              <span>{exportingJson ? "Exporting..." : "Export JSON"}</span>
            </button>
            <button
              onClick={handleExportPdf}
              disabled={exportingPdf}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-violet-600/20 hover:bg-violet-600/30 border border-violet-500/40 text-xs font-mono text-violet-300 transition-colors disabled:opacity-50"
            >
              <FileText className="w-3.5 h-3.5 text-violet-400" />
              <span>{exportingPdf ? "Generating PDF..." : "Export PDF"}</span>
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 border-t border-surface-border mt-6 pt-4 overflow-x-auto text-xs font-mono">
          <button
            onClick={() => setActiveReportTab("overview")}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              activeReportTab === "overview"
                ? "bg-surface-800 text-violet-300 border border-violet-500/40 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Overview &amp; Risk
          </button>
          <button
            onClick={() => setActiveReportTab("files")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
              activeReportTab === "files"
                ? "bg-surface-800 text-lavender-300 border border-lavender-500/40 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <span>Files &amp; Diffs</span>
            {comparison?.summary && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-surface-950 text-slate-300 border border-surface-border">
                {comparison.summary.total_package_files}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveReportTab("findings")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
              activeReportTab === "findings"
                ? "bg-surface-800 text-rose-300 border border-rose-500/40 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <span>Security Findings</span>
            {security?.findings && security.findings.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-rose-500/20 text-rose-300 border border-rose-500/30">
                {security.findings.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveReportTab("provenance")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
              activeReportTab === "provenance"
                ? "bg-surface-800 text-violet-300 border border-violet-500/40 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <span>Provenance</span>
            {provenance?.status && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-surface-950 text-slate-300 border border-surface-border">
                {provenance.status}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveReportTab("ai")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
              activeReportTab === "ai"
                ? "bg-surface-800 text-violet-300 border border-violet-500/40 font-semibold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-violet-400" />
            <span>AI Investigator</span>
          </button>
        </div>
      </div>

      {/* OVERVIEW TAB CONTENT */}
      {activeReportTab === "overview" && (
        <div className="space-y-6">
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Risk Score Dial Card */}
            <div className={`p-5 rounded-xl border ${colors.bg} ${colors.border} flex flex-col justify-between`}>
              <div>
                <span className="text-xs uppercase font-mono tracking-wider text-slate-400">
                  Risk Assessment
                </span>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className={`text-4xl font-extrabold font-mono ${colors.text}`}>
                    {score}
                  </span>
                  <span className="text-xs font-mono text-slate-400">/ 100</span>
                </div>
              </div>
              <div className="mt-4 pt-3 border-t border-surface-border text-xs font-mono text-slate-300">
                Level: <span className={`font-bold ${colors.text}`}>{level}</span>
                {risk?.confidence !== undefined && (
                  <span className="text-slate-400 block mt-0.5">
                    Confidence: {(risk.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            </div>

            {/* Differential Summary */}
            <div className="p-5 rounded-xl bg-surface-850 border border-surface-border flex flex-col justify-between">
              <div>
                <span className="text-xs uppercase font-mono tracking-wider text-slate-400">
                  Source Diffs
                </span>
                <div className="flex items-baseline gap-3 mt-2 font-mono">
                  <span className="text-2xl font-bold text-emerald-400">
                    +{comparison?.summary?.added_files ?? 0}
                  </span>
                  <span className="text-2xl font-bold text-amber-400">
                    ~{comparison?.summary?.modified_files ?? 0}
                  </span>
                  <span className="text-2xl font-bold text-slate-400">
                    ={comparison?.summary?.identical_files ?? 0}
                  </span>
                </div>
              </div>
              <div className="mt-4 pt-3 border-t border-surface-border text-xs font-mono text-slate-400">
                <span>{comparison?.summary?.total_package_files ?? 0} files in package</span>
              </div>
            </div>

            {/* Security Findings Summary */}
            <div className="p-5 rounded-xl bg-surface-850 border border-surface-border flex flex-col justify-between">
              <div>
                <span className="text-xs uppercase font-mono tracking-wider text-slate-400">
                  Static Findings
                </span>
                <div className="flex items-baseline gap-2 mt-2">
                  <span
                    className={`text-3xl font-extrabold font-mono ${
                      (security?.findings?.length ?? 0) > 0 ? "text-soc-critical" : "text-emerald-400"
                    }`}
                  >
                    {security?.findings?.length ?? 0}
                  </span>
                  <span className="text-xs font-mono text-slate-400">detected</span>
                </div>
              </div>
              <div className="mt-4 pt-3 border-t border-surface-border text-xs font-mono text-slate-400">
                <span>{security?.gaps?.length ?? 0} scanner limitations</span>
              </div>
            </div>

            {/* Provenance Card */}
            <div className="p-5 rounded-xl bg-surface-850 border border-surface-border flex flex-col justify-between">
              <div>
                <span className="text-xs uppercase font-mono tracking-wider text-slate-400">
                  Provenance
                </span>
                <div className="flex items-center gap-2 mt-2">
                  <span
                    className={`text-sm font-bold font-mono px-2.5 py-1 rounded border ${
                      provenance?.status === "VERIFIED"
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                        : provenance?.status === "NOT_VERIFIED"
                        ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                        : "bg-surface-800 text-slate-300 border-surface-border"
                    }`}
                  >
                    {provenance?.status || "UNAVAILABLE"}
                  </span>
                </div>
              </div>
              <div className="mt-4 pt-3 border-t border-surface-border text-xs font-mono text-slate-400 truncate">
                <span>{provenance?.sigstore_verified ? "Sigstore Verified" : "Unsigned Build"}</span>
              </div>
            </div>
          </div>

          {/* Release Comparison / Evolution Card (when previous release exists) */}
          {comparisonData && comparisonData.base_version !== "none" && (
            <div className="p-5 rounded-xl bg-surface-850 border border-surface-border space-y-3">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-surface-border pb-3">
                <div className="flex items-center gap-2">
                  <GitBranch className="w-4 h-4 text-violet-400" />
                  <h3 className="font-mono text-sm font-semibold text-white">
                    Release Evolution: {comparisonData.base_version} → {comparisonData.head_version}
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1 text-xs font-mono px-2.5 py-0.5 rounded-full border ${
                      comparisonData.risk_change.is_elevated
                        ? "bg-rose-500/20 text-rose-300 border-rose-500/30"
                        : comparisonData.risk_change.score_delta < 0
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                        : "bg-surface-800 text-slate-400 border-surface-border"
                    }`}
                  >
                    {comparisonData.risk_change.score_delta > 0 ? (
                      <TrendingUp className="w-3.5 h-3.5" />
                    ) : comparisonData.risk_change.score_delta < 0 ? (
                      <TrendingDown className="w-3.5 h-3.5" />
                    ) : null}
                    Risk: {comparisonData.risk_change.score_delta > 0 ? `+${comparisonData.risk_change.score_delta}` : comparisonData.risk_change.score_delta} pts ({comparisonData.risk_change.base_score ?? 0} → {comparisonData.risk_change.head_score ?? 0})
                  </span>
                </div>
              </div>

              <p className="text-xs font-mono text-slate-300 leading-relaxed">
                {comparisonData.summary}
              </p>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs font-mono">
                <div className="p-2.5 rounded-lg bg-surface-900 border border-surface-border">
                  <span className="text-slate-400 block">Newly Added</span>
                  <span className="text-base font-bold text-emerald-400">
                    +{comparisonData.file_changes.newly_added.length}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-surface-900 border border-surface-border">
                  <span className="text-slate-400 block">Newly Modified</span>
                  <span className="text-base font-bold text-amber-400">
                    ~{comparisonData.file_changes.newly_modified.length}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-surface-900 border border-surface-border">
                  <span className="text-slate-400 block">New Findings</span>
                  <span className={`text-base font-bold ${comparisonData.finding_changes.new_findings.length > 0 ? "text-soc-critical" : "text-slate-400"}`}>
                    {comparisonData.finding_changes.new_findings.length}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-surface-900 border border-surface-border">
                  <span className="text-slate-400 block">Suspicious Artifacts</span>
                  <span className={`text-base font-bold ${comparisonData.file_changes.new_suspicious_artifacts.length > 0 ? "text-soc-critical" : "text-emerald-400"}`}>
                    {comparisonData.file_changes.new_suspicious_artifacts.length}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Hard Floors Notice (if triggered) */}
          {risk?.floors && risk.floors.some((f) => f.triggered) && (
            <div className="p-4 rounded-xl bg-soc-critical-bg border border-soc-critical-border space-y-2">
              <div className="flex items-center gap-2 text-soc-critical font-mono font-bold text-sm">
                <AlertOctagon className="w-4 h-4" />
                <span>Deterministic Hard Security Floor Triggered</span>
              </div>
              <div className="space-y-1.5 text-xs font-mono text-rose-200">
                {risk.floors
                  .filter((f) => f.triggered)
                  .map((floor, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-soc-critical font-bold">•</span>
                      <span>
                        <strong>{floor.name}</strong>: Enforced floor of {floor.min_score} points ({floor.reason})
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Contributing Factors & Recommendations 2-Column */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Contributing Factors */}
            <div className="p-5 rounded-xl bg-surface-850 border border-surface-border space-y-4">
              <div className="flex items-center justify-between border-b border-surface-border pb-3">
                <h3 className="font-mono text-sm font-semibold text-white flex items-center gap-2">
                  <Layers className="w-4 h-4 text-violet-400" />
                  Contributing Risk Factors
                </h3>
                <span className="text-xs font-mono text-slate-400">
                  {risk?.factors?.length ?? 0} factors
                </span>
              </div>

              {risk?.factors && risk.factors.length > 0 ? (
                <div className="space-y-2.5">
                  {risk.factors.map((f, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-lg bg-surface-950 border border-surface-border text-xs font-mono flex items-start justify-between gap-3"
                    >
                      <div>
                        <span className="font-semibold text-slate-200">{f.factor}</span>
                        <p className="text-slate-400 mt-0.5">{f.details}</p>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded font-bold ${
                          f.points > 20
                            ? "bg-rose-500/20 text-rose-300"
                            : f.points > 0
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-surface-800 text-slate-400"
                        }`}
                      >
                        +{f.points}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 font-mono py-4 text-center">
                  No elevated risk factors detected.
                </p>
              )}
            </div>

            {/* Recommendations & Limitations */}
            <div className="p-5 rounded-xl bg-surface-850 border border-surface-border space-y-4">
              <div className="flex items-center justify-between border-b border-surface-border pb-3">
                <h3 className="font-mono text-sm font-semibold text-white flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-lavender-400" />
                  Actionable Recommendations
                </h3>
              </div>

              {risk?.recommendations && risk.recommendations.length > 0 ? (
                <ul className="space-y-2">
                  {risk.recommendations.map((rec, i) => (
                    <li
                      key={i}
                      className="p-3 rounded-lg bg-surface-950 border border-surface-border text-xs font-mono text-slate-300 flex items-start gap-2.5"
                    >
                      <CheckCircle2 className="w-4 h-4 text-violet-400 shrink-0 mt-0.5" />
                      <span>{rec}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400 font-mono py-4 text-center">
                  No specific recommendations necessary. Package appears standard.
                </p>
              )}

              {/* Limitations Disclosure */}
              {risk?.limitations && risk.limitations.length > 0 && (
                <div className="pt-2 border-t border-surface-border">
                  <h4 className="text-[11px] uppercase font-mono tracking-wider text-slate-400 mb-2">
                    Analysis Limitations
                  </h4>
                  <ul className="space-y-1 text-xs font-mono text-slate-400">
                    {risk.limitations.map((lim, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-slate-500">•</span>
                        <span>{lim}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
