"use client";

import React, { useState } from "react";
import {
  Search,
  AlertCircle,
  BookmarkPlus,
  Loader2,
  Terminal,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Ecosystem, ScanRequest } from "../lib/types";

interface ScannerFormProps {
  onSubmit: (request: ScanRequest) => Promise<void>;
  isLoading: boolean;
  initialEcosystem?: Ecosystem;
  initialPackage?: string;
  initialVersion?: string;
  onAddToWatchlist?: (ecosystem: Ecosystem, packageName: string) => void;
}

const NPM_REGEX = /^(?:@[a-z0-9][a-z0-9._~-]*\/)?[A-Za-z0-9][A-Za-z0-9._~-]*$/;
const PYPI_REGEX = /^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$/;
const SEMVER_REGEX =
  /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-(?:(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$/;

const SAMPLE_PRESETS: { ecosystem: Ecosystem; name: string; version: string; note: string }[] = [
  { ecosystem: "npm", name: "left-pad", version: "1.3.0", note: "Clean npm package" },
  { ecosystem: "npm", name: "chalk", version: "5.3.0", note: "ESM bundled release" },
  { ecosystem: "npm", name: "event-stream", version: "3.3.6", note: "flatmap-stream incident" },
  { ecosystem: "pypi", name: "requests", version: "2.31.0", note: "Authoritative PyPI lib" },
];

export function ScannerForm({
  onSubmit,
  isLoading,
  initialEcosystem = "npm",
  initialPackage = "",
  initialVersion = "",
  onAddToWatchlist,
}: ScannerFormProps) {
  const [ecosystem, setEcosystem] = useState<Ecosystem>(initialEcosystem);
  const [packageName, setPackageName] = useState<string>(initialPackage);
  const [version, setVersion] = useState<string>(initialVersion);
  const [validationError, setValidationError] = useState<string | null>(null);

  function validate(): string | null {
    const trimmedPkg = packageName.trim();
    const trimmedVer = version.trim();

    if (!trimmedPkg) {
      return "Package name is required.";
    }
    if (!trimmedVer) {
      return "Exact version is required. Veritor requires exact published versions (tags such as 'latest' are rejected).";
    }
    if (trimmedVer.toLowerCase() === "latest") {
      return "Tags like 'latest' are not supported. Specify an exact version (e.g. 1.3.0).";
    }

    if (ecosystem === "npm") {
      if (!NPM_REGEX.test(trimmedPkg)) {
        return "Invalid npm package name format (e.g. 'express' or '@types/node').";
      }
      if (!SEMVER_REGEX.test(trimmedVer)) {
        return "Invalid npm version. Must be an exact semantic version (e.g. '1.3.0' or '2.0.0-rc.1').";
      }
    } else {
      if (!PYPI_REGEX.test(trimmedPkg)) {
        return "Invalid PyPI package name format (e.g. 'requests' or 'urllib3').";
      }
      if (!/^\d+(\.\d+)*((\.dev|rc|a|b|post)\d+)?$/.test(trimmedVer)) {
        return "Invalid PyPI version format (PEP 440, e.g. '2.31.0').";
      }
    }

    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const err = validate();
    if (err) {
      setValidationError(err);
      return;
    }
    setValidationError(null);

    await onSubmit({
      ecosystem,
      package_name: packageName.trim(),
      version: version.trim(),
    });
  }

  function applyPreset(preset: (typeof SAMPLE_PRESETS)[0]) {
    setEcosystem(preset.ecosystem);
    setPackageName(preset.name);
    setVersion(preset.version);
    setValidationError(null);
  }

  return (
    <div className="w-full max-w-3xl mx-auto my-6 p-5 sm:p-6 rounded-xl bg-surface-850 border border-surface-border shadow-2xl relative">
      {/* Top Header & Ecosystem Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 border-b border-surface-border pb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded bg-violet-950/50 border border-violet-800 text-violet-400">
            <Terminal className="w-4 h-4" />
          </div>
          <div>
            <h2 className="font-semibold text-sm sm:text-base tracking-wide text-white font-mono">
              Package Integrity Scanner
            </h2>
            <p className="text-xs text-slate-400">
              Verify published distribution tarballs against signed Git source trees
            </p>
          </div>
        </div>

        {/* Ecosystem Switcher */}
        <div className="flex items-center gap-1.5 bg-surface-950 p-1 rounded-lg border border-surface-border self-start sm:self-center">
          <button
            type="button"
            onClick={() => setEcosystem("npm")}
            className={`px-3 py-1 rounded text-xs font-mono font-medium transition-all ${
              ecosystem === "npm"
                ? "bg-violet-600/25 text-violet-300 border border-violet-500/50 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            npm
          </button>
          <button
            type="button"
            onClick={() => setEcosystem("pypi")}
            className={`px-3 py-1 rounded text-xs font-mono font-medium transition-all ${
              ecosystem === "pypi"
                ? "bg-violet-600/25 text-violet-300 border border-violet-500/50 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            PyPI
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="sm:col-span-2 space-y-1">
            <label className="block text-xs font-mono text-slate-400 font-semibold tracking-wider">
              PACKAGE NAME
            </label>
            <div className="relative">
              <input
                type="text"
                value={packageName}
                onChange={(e) => {
                  setPackageName(e.target.value);
                  if (validationError) setValidationError(null);
                }}
                placeholder={
                  ecosystem === "npm"
                    ? "e.g. left-pad, @types/node"
                    : "e.g. requests, urllib3"
                }
                className="w-full px-3.5 py-2.5 rounded-lg bg-surface-950 border border-surface-border text-slate-100 placeholder-slate-600 font-mono text-sm focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition-colors"
                disabled={isLoading}
                required
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="block text-xs font-mono text-slate-400 font-semibold tracking-wider">
              EXACT VERSION
            </label>
            <input
              type="text"
              value={version}
              onChange={(e) => {
                setVersion(e.target.value);
                if (validationError) setValidationError(null);
              }}
              placeholder={ecosystem === "npm" ? "1.3.0" : "2.31.0"}
              className="w-full px-3.5 py-2.5 rounded-lg bg-surface-950 border border-surface-border text-slate-100 placeholder-slate-600 font-mono text-sm focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition-colors"
              disabled={isLoading}
              required
            />
          </div>
        </div>

        {/* Quick Sample Presets */}
        <div className="flex flex-wrap items-center gap-2 pt-1 pb-1">
          <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-lavender-400" />
            Quick Presets:
          </span>
          {SAMPLE_PRESETS.map((preset) => (
            <button
              key={`${preset.ecosystem}-${preset.name}`}
              type="button"
              disabled={isLoading}
              onClick={() => applyPreset(preset)}
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-800 hover:bg-surface-750 border border-surface-border hover:border-violet-500/50 text-[11px] font-mono text-slate-300 hover:text-violet-300 transition-colors"
            >
              <span>{preset.name}</span>
              <span className="text-slate-400">@{preset.version}</span>
            </button>
          ))}
        </div>

        {validationError && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-soc-critical-bg border border-soc-critical-border text-rose-300 text-xs font-mono animate-fadeIn">
            <AlertCircle className="w-4 h-4 shrink-0 text-soc-critical" />
            <span>{validationError}</span>
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-surface-border">
          <div className="flex items-center gap-2">
            {onAddToWatchlist && packageName.trim() && (
              <button
                type="button"
                onClick={() => onAddToWatchlist(ecosystem, packageName.trim())}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-800 hover:bg-surface-750 border border-surface-border text-xs text-slate-300 transition-colors font-medium font-mono"
              >
                <BookmarkPlus className="w-3.5 h-3.5 text-lavender-400" />
                <span>Add to Watchlist</span>
              </button>
            )}
            <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-400 font-mono">
              <ShieldCheck className="w-3.5 h-3.5 text-violet-400" />
              <span>Zero-code execution guarantee.</span>
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-500 active:bg-violet-700 text-white font-medium text-sm font-mono transition-all shadow-lg shadow-violet-950/60 disabled:opacity-50 disabled:cursor-not-allowed group"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-violet-200" />
                <span>Analyzing Package...</span>
              </>
            ) : (
              <>
                <Search className="w-4 h-4 text-violet-200 group-hover:scale-110 transition-transform" />
                <span>Scan Package</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
