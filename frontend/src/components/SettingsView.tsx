"use client";

import React, { useState, useEffect } from "react";
import {
  Settings,
  Server,
  Cpu,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Save,
  ShieldCheck,
} from "lucide-react";
import {
  checkBackendHealth,
  checkOllamaConnection,
  getApiBaseUrl,
  setApiBaseUrl,
} from "../lib/api";

export function SettingsView() {
  const [apiUrl, setApiUrl] = useState(() => getApiBaseUrl());
  const [ollamaUrl, setOllamaUrl] = useState("http://127.0.0.1:11434");
  const [backendStatus, setBackendStatus] = useState<string>("checking");
  const [ollamaStatus, setOllamaStatus] = useState<boolean | null>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [isSaved, setIsSaved] = useState(false);
  const [isTesting, setIsTesting] = useState(false);

  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      try {
        const backend = await checkBackendHealth();
        if (mounted) setBackendStatus(backend.status);
      } catch {
        if (mounted) setBackendStatus("disconnected");
      }

      try {
        const ollama = await checkOllamaConnection(ollamaUrl);
        if (mounted) {
          setOllamaStatus(ollama.connected);
          setOllamaModels(ollama.models);
        }
      } catch {
        if (mounted) {
          setOllamaStatus(false);
          setOllamaModels([]);
        }
      }
    };

    fetchStatus();
    return () => {
      mounted = false;
    };
  }, [ollamaUrl]);

  async function testConnections() {
    setIsTesting(true);
    try {
      const backend = await checkBackendHealth();
      setBackendStatus(backend.status);
    } catch {
      setBackendStatus("disconnected");
    }

    try {
      const ollama = await checkOllamaConnection(ollamaUrl);
      setOllamaStatus(ollama.connected);
      setOllamaModels(ollama.models);
    } catch {
      setOllamaStatus(false);
      setOllamaModels([]);
    }
    setIsTesting(false);
  }

  function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setApiBaseUrl(apiUrl);
    setIsSaved(true);
    testConnections();
    setTimeout(() => setIsSaved(false), 2500);
  }

  return (
    <div className="w-full max-w-3xl mx-auto my-6 p-6 rounded-xl bg-surface-850 border border-surface-border shadow-xl space-y-6 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-surface-border pb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded bg-violet-950/60 border border-violet-800 text-violet-400">
            <Settings className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">Settings &amp; Infrastructure</h2>
            <p className="text-slate-400 text-[11px]">Configure API endpoints and local LLM telemetry</p>
          </div>
        </div>
        <button
          onClick={testConnections}
          disabled={isTesting}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-800 hover:bg-surface-750 border border-surface-border text-slate-300 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isTesting ? "animate-spin" : ""}`} />
          <span>Test Connectivity</span>
        </button>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Backend API Configuration */}
        <div className="p-4 rounded-xl bg-surface-900 border border-surface-border space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-white font-semibold">
              <Server className="w-4 h-4 text-violet-400" />
              <span>Veritor FastAPI Backend</span>
            </div>
            <div className="flex items-center gap-1.5">
              {backendStatus === "ok" ? (
                <span className="inline-flex items-center gap-1 text-emerald-400 font-semibold">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>HEALTHY</span>
                </span>
              ) : backendStatus === "checking" ? (
                <span className="text-slate-500 animate-pulse">CHECKING...</span>
              ) : (
                <span className="inline-flex items-center gap-1 text-soc-critical font-semibold">
                  <XCircle className="w-3.5 h-3.5" />
                  <span>UNREACHABLE</span>
                </span>
              )}
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-[11px] text-slate-400">
              API Base URL
            </label>
            <input
              type="text"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="http://127.0.0.1:8000"
              className="w-full px-3 py-2 rounded-lg bg-surface-950 border border-surface-border text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-500"
            />
          </div>
        </div>

        {/* Local Ollama Configuration */}
        <div className="p-4 rounded-xl bg-surface-900 border border-surface-border space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-white font-semibold">
              <Cpu className="w-4 h-4 text-lavender-400" />
              <span>Local Ollama LLM Service</span>
            </div>
            <div className="flex items-center gap-1.5">
              {ollamaStatus === true ? (
                <span className="inline-flex items-center gap-1 text-violet-300 font-semibold">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>CONNECTED</span>
                </span>
              ) : ollamaStatus === false ? (
                <span className="inline-flex items-center gap-1 text-slate-500 font-semibold">
                  <XCircle className="w-3.5 h-3.5" />
                  <span>OFFLINE</span>
                </span>
              ) : (
                <span className="text-slate-500 animate-pulse">CHECKING...</span>
              )}
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-[11px] text-slate-400">
              Ollama Host URL
            </label>
            <input
              type="text"
              value={ollamaUrl}
              onChange={(e) => setOllamaUrl(e.target.value)}
              placeholder="http://127.0.0.1:11434"
              className="w-full px-3 py-2 rounded-lg bg-surface-950 border border-surface-border text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-500"
            />
          </div>

          {ollamaModels.length > 0 && (
            <div className="pt-2 border-t border-surface-border">
              <span className="text-[11px] text-slate-400 block mb-1.5">
                Available Local Models:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {ollamaModels.map((m) => (
                  <span
                    key={m}
                    className="px-2 py-0.5 rounded text-[10px] bg-violet-950/60 border border-violet-800 text-violet-300"
                  >
                    {m}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Security & Isolation Summary */}
        <div className="p-4 rounded-xl bg-surface-900 border border-surface-border text-slate-300 space-y-1.5">
          <div className="flex items-center gap-2 text-violet-300 font-bold">
            <ShieldCheck className="w-4 h-4" />
            <span>Zero-Execution Architecture</span>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            All tarball extractions occur in transient isolated directories under chroot/sandbox boundaries.
            Neither npm nor pip lifecycle scripts are ever invoked.
          </p>
        </div>

        {/* Action Button */}
        <div className="flex items-center justify-between pt-2">
          {isSaved && (
            <span className="text-emerald-400 font-bold animate-fadeIn">
              ✓ Settings saved successfully.
            </span>
          )}
          <div className="ml-auto">
            <button
              type="submit"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-500 active:bg-violet-700 text-white font-semibold transition-all shadow-md shadow-violet-950/60"
            >
              <Save className="w-4 h-4" />
              <span>Save Configuration</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
