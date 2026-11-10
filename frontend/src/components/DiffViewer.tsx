"use client";

import React, { useMemo, useState } from "react";
import {
  Copy,
  Check,
  Columns,
  AlignJustify,
  FileCode,
  FileCheck,
  FilePlus,
  FileMinus,
  Binary,
} from "lucide-react";
import { FileDiffItem } from "../lib/types";

export interface DiffViewerProps {
  diff: FileDiffItem | null;
  isLoading: boolean;
  filePath: string;
  initialViewMode?: "unified" | "split";
}

interface SplitCell {
  lineNumber?: number;
  content: string;
  type: "context" | "addition" | "deletion" | "empty";
}

interface SplitRow {
  type: "header" | "data";
  headerText?: string;
  left?: SplitCell;
  right?: SplitCell;
}

interface UnifiedRow {
  type: "header" | "context" | "addition" | "deletion" | "info";
  oldLineNumber?: number;
  newLineNumber?: number;
  content: string;
}

const KEYWORDS = new Set([
  "const",
  "let",
  "var",
  "function",
  "return",
  "class",
  "import",
  "export",
  "from",
  "default",
  "async",
  "await",
  "if",
  "else",
  "for",
  "while",
  "try",
  "catch",
  "finally",
  "throw",
  "new",
  "typeof",
  "instanceof",
  "def",
  "elif",
  "with",
  "as",
  "lambda",
  "pass",
  "yield",
  "raise",
  "package",
  "struct",
  "interface",
  "type",
  "public",
  "private",
  "protected",
  "static",
  "extends",
  "implements",
]);

const LITERALS = new Set([
  "true",
  "false",
  "null",
  "undefined",
  "None",
  "True",
  "False",
  "nil",
]);

export function highlightTokens(line: string): React.ReactNode {
  if (!line) return " ";
  const regex =
    /(\/\/[^\n]*|#[^\n]*|\"(?:\\\"|[^\"])*\"|'(?:\\'|[^'])*'|`[^`]*`|[a-zA-Z_$][a-zA-Z0-9_$]*|\b\d+(?:\.\d+)?\b|[^\s\w]+|\s+)/g;
  const parts: React.ReactNode[] = [];
  let match: RegExpExecArray | null;
  let idx = 0;

  while ((match = regex.exec(line)) !== null) {
    const text = match[0];
    const key = `tok-${idx++}`;
    if (text.startsWith("//") || text.startsWith("#") || text.startsWith("/*")) {
      parts.push(
        <span key={key} className="text-slate-500 italic">
          {text}
        </span>
      );
    } else if (text.startsWith('"') || text.startsWith("'") || text.startsWith("`")) {
      parts.push(
        <span key={key} className="text-emerald-300/90">
          {text}
        </span>
      );
    } else if (KEYWORDS.has(text)) {
      parts.push(
        <span key={key} className="text-purple-400 font-semibold">
          {text}
        </span>
      );
    } else if (LITERALS.has(text)) {
      parts.push(
        <span key={key} className="text-cyan-400 font-semibold">
          {text}
        </span>
      );
    } else if (/^\d+(\.\d+)?$/.test(text)) {
      parts.push(
        <span key={key} className="text-amber-400">
          {text}
        </span>
      );
    } else {
      parts.push(<span key={key}>{text}</span>);
    }
  }

  return parts.length > 0 ? parts : line;
}

export function parseUnifiedDiff(raw: string): {
  unifiedRows: UnifiedRow[];
  splitRows: SplitRow[];
} {
  if (!raw || !raw.trim()) {
    return { unifiedRows: [], splitRows: [] };
  }

  const lines = raw.split("\n");
  const unifiedRows: UnifiedRow[] = [];
  const splitRows: SplitRow[] = [];

  let oldLine = 1;
  let newLine = 1;
  let inHunk = false;

  let delBatch: { line: number; text: string }[] = [];
  let addBatch: { line: number; text: string }[] = [];

  function flushBatches() {
    if (delBatch.length === 0 && addBatch.length === 0) return;
    const max = Math.max(delBatch.length, addBatch.length);
    for (let i = 0; i < max; i++) {
      const del = delBatch[i];
      const add = addBatch[i];
      splitRows.push({
        type: "data",
        left: del
          ? { lineNumber: del.line, content: del.text, type: "deletion" }
          : { type: "empty", content: "" },
        right: add
          ? { lineNumber: add.line, content: add.text, type: "addition" }
          : { type: "empty", content: "" },
      });
    }
    delBatch = [];
    addBatch = [];
  }

  for (const line of lines) {
    if (line.startsWith("@@")) {
      flushBatches();
      const match = line.match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)/);
      if (match) {
        oldLine = parseInt(match[1], 10);
        newLine = parseInt(match[3], 10);
        inHunk = true;
      }
      unifiedRows.push({ type: "header", content: line });
      splitRows.push({ type: "header", headerText: line });
      continue;
    }

    if (!inHunk) {
      if (
        line.startsWith("---") ||
        line.startsWith("+++") ||
        line.startsWith("diff") ||
        line.startsWith("index")
      ) {
        unifiedRows.push({ type: "info", content: line });
      }
      continue;
    }

    if (line.startsWith("-")) {
      const text = line.slice(1);
      delBatch.push({ line: oldLine++, text });
      unifiedRows.push({
        type: "deletion",
        oldLineNumber: oldLine - 1,
        content: text,
      });
    } else if (line.startsWith("+")) {
      const text = line.slice(1);
      addBatch.push({ line: newLine++, text });
      unifiedRows.push({
        type: "addition",
        newLineNumber: newLine - 1,
        content: text,
      });
    } else if (line.startsWith("\\")) {
      flushBatches();
      unifiedRows.push({ type: "info", content: line });
    } else {
      flushBatches();
      const text = line.startsWith(" ") ? line.slice(1) : line;
      unifiedRows.push({
        type: "context",
        oldLineNumber: oldLine,
        newLineNumber: newLine,
        content: text,
      });
      splitRows.push({
        type: "data",
        left: { lineNumber: oldLine++, content: text, type: "context" },
        right: { lineNumber: newLine++, content: text, type: "context" },
      });
    }
  }

  flushBatches();
  return { unifiedRows, splitRows };
}

export function DiffViewer({
  diff,
  isLoading,
  filePath,
  initialViewMode = "unified",
}: DiffViewerProps) {
  const [viewMode, setViewMode] = useState<"unified" | "split">(initialViewMode);
  const [copied, setCopied] = useState(false);

  const { unifiedRows, splitRows } = useMemo(() => {
    return parseUnifiedDiff(diff?.unified || "");
  }, [diff?.unified]);

  function copyDiff() {
    if (!diff?.unified) return;
    navigator.clipboard.writeText(diff.unified);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (isLoading) {
    return (
      <div
        data-testid="diff-viewer-loading"
        className="w-full h-full min-h-[400px] flex items-center justify-center bg-surface-850 rounded-xl border border-surface-border p-8"
      >
        <div className="flex flex-col items-center gap-3 text-slate-400 font-mono text-xs">
          <div className="w-6 h-6 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <span>Loading diff for {filePath}...</span>
        </div>
      </div>
    );
  }

  if (!diff) {
    return (
      <div
        data-testid="diff-viewer-empty"
        className="w-full h-full min-h-[400px] flex items-center justify-center bg-surface-850 rounded-xl border border-surface-border p-8 text-center text-slate-500 font-mono text-xs"
      >
        <div className="space-y-2">
          <FileCode className="w-8 h-8 mx-auto text-slate-600" />
          <p>Select a file from the explorer to view differences.</p>
        </div>
      </div>
    );
  }

  const isIdentical =
    diff.diff_status === "CLEAN" || (!diff.unified && diff.status === "IDENTICAL");
  const isBinary = diff.diff_status === "BINARY";
  const isAdded = diff.status === "ADDED";
  const isRemoved = diff.status === "REMOVED";
  const hasDiffContent = unifiedRows.length > 0;

  return (
    <div
      data-testid="diff-viewer"
      className="w-full h-full flex flex-col bg-surface-950 rounded-xl border border-surface-border overflow-hidden font-mono text-xs shadow-xl"
    >
      {/* Diff Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-surface-850 border-b border-surface-border">
        <div className="flex items-center gap-2 truncate">
          <FileCode className="w-4 h-4 text-violet-400 shrink-0" />
          <span className="font-bold text-white truncate">{filePath}</span>
          <span
            className={`text-[10px] px-2 py-0.5 rounded border ${
              isAdded
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                : isRemoved
                ? "bg-rose-500/20 text-rose-300 border-rose-500/30"
                : diff.status === "MODIFIED"
                ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                : "bg-surface-800 text-slate-400 border-surface-border"
            }`}
          >
            {diff.status}
          </span>
          {isAdded && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800 hidden sm:inline-flex items-center gap-1">
              <FilePlus className="w-3 h-3" /> Missing in Source
            </span>
          )}
          {isRemoved && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-rose-950/60 text-rose-400 border border-rose-800 hidden sm:inline-flex items-center gap-1">
              <FileMinus className="w-3 h-3" /> Removed in Package
            </span>
          )}
          {diff.classification && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-violet-950/60 text-violet-300 border border-violet-800">
              {diff.classification}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Additions / Removals Counter */}
          <div className="flex items-center gap-2 text-xs">
            {diff.added_lines !== undefined && diff.added_lines !== null && (
              <span className="text-emerald-400 font-semibold">+{diff.added_lines}</span>
            )}
            {diff.removed_lines !== undefined && diff.removed_lines !== null && (
              <span className="text-rose-400 font-semibold">-{diff.removed_lines}</span>
            )}
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center bg-surface-950 p-0.5 rounded-lg border border-surface-border">
            <button
              data-testid="toggle-unified"
              onClick={() => setViewMode("unified")}
              className={`flex items-center gap-1 px-2 py-1 rounded transition-colors text-xs ${
                viewMode === "unified"
                  ? "bg-surface-800 text-violet-200 ring-1 ring-violet-500/40 shadow"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              title="Unified View"
            >
              <AlignJustify className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Unified</span>
            </button>
            <button
              data-testid="toggle-split"
              onClick={() => setViewMode("split")}
              className={`flex items-center gap-1 px-2 py-1 rounded transition-colors text-xs ${
                viewMode === "split"
                  ? "bg-surface-800 text-violet-200 ring-1 ring-violet-500/40 shadow"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              title="Side-by-side View"
            >
              <Columns className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Side-by-side</span>
            </button>
          </div>

          {/* Copy Button */}
          {diff.unified && (
            <button
              onClick={copyDiff}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-surface-800 hover:bg-surface-750 border border-surface-border text-slate-300 transition-colors"
              title="Copy diff to clipboard"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="hidden sm:inline">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-slate-400" />
                  <span className="hidden sm:inline">Copy</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Diff Content Body */}
      <div className="flex-1 overflow-x-auto overflow-y-auto max-h-[650px] text-xs font-mono leading-relaxed bg-slate-950">
        {isIdentical ? (
          <div data-testid="diff-identical" className="py-20 text-center text-slate-500 space-y-2.5">
            <FileCheck className="w-9 h-9 mx-auto text-emerald-400/80" />
            <p className="text-slate-200 font-semibold text-sm">
              File is identical between source repository and published package.
            </p>
            <p className="text-slate-500 text-[11px]">
              Zero unexpected modifications or injected payloads detected.
            </p>
          </div>
        ) : isBinary ? (
          <div data-testid="diff-binary" className="py-20 text-center text-slate-500 space-y-2.5">
            <Binary className="w-9 h-9 mx-auto text-cyan-400/80" />
            <p className="text-slate-200 font-semibold text-sm">
              Binary file (diff cannot be displayed in text view).
            </p>
            <p className="text-slate-500 text-[11px]">
              Binary files are scanned via checksum verification and safe archive rules.
            </p>
          </div>
        ) : hasDiffContent ? (
          viewMode === "unified" ? (
            /* UNIFIED DIFF TABLE */
            <table data-testid="unified-diff-table" className="w-full border-collapse">
              <tbody>
                {unifiedRows.map((row, idx) => {
                  if (row.type === "header") {
                    return (
                      <tr
                        key={idx}
                        className="bg-slate-900/90 text-cyan-400 font-semibold border-y border-slate-800"
                      >
                        <td className="w-10 px-2 py-1 text-center select-none text-slate-600 border-r border-slate-800 text-[11px]">
                          ...
                        </td>
                        <td className="w-10 px-2 py-1 text-center select-none text-slate-600 border-r border-slate-800 text-[11px]">
                          ...
                        </td>
                        <td className="pl-3 pr-2 py-1 whitespace-pre font-mono text-[11px] text-cyan-400/90">
                          {row.content}
                        </td>
                      </tr>
                    );
                  }

                  if (row.type === "info") {
                    return (
                      <tr key={idx} className="bg-slate-900/40 text-slate-500 italic">
                        <td className="w-10 px-2 py-0.5 border-r border-slate-800 select-none text-[11px]" />
                        <td className="w-10 px-2 py-0.5 border-r border-slate-800 select-none text-[11px]" />
                        <td className="pl-3 pr-2 py-0.5 whitespace-pre font-mono text-[11px]">
                          {row.content}
                        </td>
                      </tr>
                    );
                  }

                  const isAdd = row.type === "addition";
                  const isDel = row.type === "deletion";
                  const rowBg = isAdd
                    ? "bg-emerald-950/30 hover:bg-emerald-950/40 text-emerald-200"
                    : isDel
                    ? "bg-rose-950/30 hover:bg-rose-950/40 text-rose-200"
                    : "text-slate-300 hover:bg-slate-900/40";

                  const marker = isAdd ? "+" : isDel ? "-" : " ";
                  const markerColor = isAdd
                    ? "text-emerald-400 font-bold"
                    : isDel
                    ? "text-rose-400 font-bold"
                    : "text-slate-600";

                  return (
                    <tr key={idx} className={`border-b border-slate-900/50 ${rowBg}`}>
                      {/* Old Line Number (Source) */}
                      <td className="w-12 px-2 py-0.5 text-right select-none text-slate-600 border-r border-slate-800 text-[11px] font-mono bg-slate-950/30">
                        {row.oldLineNumber ?? ""}
                      </td>
                      {/* New Line Number (Package) */}
                      <td className="w-12 px-2 py-0.5 text-right select-none text-slate-600 border-r border-slate-800 text-[11px] font-mono bg-slate-950/30">
                        {row.newLineNumber ?? ""}
                      </td>
                      {/* Code Content */}
                      <td className="pl-2 pr-4 py-0.5 whitespace-pre font-mono text-[11px]">
                        <span className={`select-none inline-block w-4 ${markerColor}`}>
                          {marker}
                        </span>
                        {highlightTokens(row.content)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            /* SIDE-BY-SIDE (SPLIT) DIFF TABLE */
            <div data-testid="split-diff-view" className="w-full min-w-[700px]">
              {/* Split Header Pane Labels */}
              <div className="grid grid-cols-2 bg-slate-900/80 border-b border-slate-800 text-xs font-semibold text-slate-400 select-none sticky top-0 z-10">
                <div className="flex items-center justify-between px-4 py-1.5 border-r border-slate-800">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-rose-500/80" />
                    <span>Source Repository (Original)</span>
                  </div>
                  {isAdded && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      File Absent
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between px-4 py-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-500/80" />
                    <span>Published Package (Artifact)</span>
                  </div>
                  {isRemoved && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">
                      File Removed
                    </span>
                  )}
                </div>
              </div>

              <table data-testid="split-diff-table" className="w-full border-collapse">
                <tbody>
                  {splitRows.map((row, idx) => {
                    if (row.type === "header") {
                      return (
                        <tr
                          key={idx}
                          className="bg-slate-900/90 text-cyan-400 font-semibold border-y border-slate-800"
                        >
                          <td
                            colSpan={4}
                            className="px-4 py-1 whitespace-pre font-mono text-[11px] text-cyan-400/90"
                          >
                            {row.headerText}
                          </td>
                        </tr>
                      );
                    }

                    const left = row.left;
                    const right = row.right;

                    const leftIsDel = left?.type === "deletion";
                    const leftIsEmpty = left?.type === "empty";
                    const leftBg = leftIsDel
                      ? "bg-rose-950/30 text-rose-200"
                      : leftIsEmpty
                      ? "bg-slate-950/40 text-transparent select-none"
                      : "text-slate-300";

                    const rightIsAdd = right?.type === "addition";
                    const rightIsEmpty = right?.type === "empty";
                    const rightBg = rightIsAdd
                      ? "bg-emerald-950/30 text-emerald-200"
                      : rightIsEmpty
                      ? "bg-slate-950/40 text-transparent select-none"
                      : "text-slate-300";

                    return (
                      <tr key={idx} className="border-b border-slate-900/40">
                        {/* LEFT: Line Number */}
                        <td className="w-12 px-2 py-0.5 text-right select-none text-slate-600 border-r border-slate-800 text-[11px] font-mono bg-slate-950/40">
                          {left?.lineNumber ?? ""}
                        </td>
                        {/* LEFT: Code Text */}
                        <td
                          className={`w-[calc(50%-3rem)] px-2 py-0.5 whitespace-pre font-mono text-[11px] border-r border-slate-800 ${leftBg}`}
                        >
                          {!leftIsEmpty && (
                            <>
                              <span
                                className={`select-none inline-block w-3.5 ${
                                  leftIsDel ? "text-rose-400 font-bold" : "text-slate-600"
                                }`}
                              >
                                {leftIsDel ? "-" : " "}
                              </span>
                              {highlightTokens(left?.content || "")}
                            </>
                          )}
                        </td>

                        {/* RIGHT: Line Number */}
                        <td className="w-12 px-2 py-0.5 text-right select-none text-slate-600 border-r border-slate-800 text-[11px] font-mono bg-slate-950/40">
                          {right?.lineNumber ?? ""}
                        </td>
                        {/* RIGHT: Code Text */}
                        <td
                          className={`w-[calc(50%-3rem)] px-2 py-0.5 whitespace-pre font-mono text-[11px] ${rightBg}`}
                        >
                          {!rightIsEmpty && (
                            <>
                              <span
                                className={`select-none inline-block w-3.5 ${
                                  rightIsAdd ? "text-emerald-400 font-bold" : "text-slate-600"
                                }`}
                              >
                                {rightIsAdd ? "+" : " "}
                              </span>
                              {highlightTokens(right?.content || "")}
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        ) : (
          <div data-testid="diff-no-content" className="py-20 text-center text-slate-500 space-y-2">
            <FileCode className="w-8 h-8 mx-auto text-slate-600" />
            <p className="text-slate-300">No textual diff content returned for this file.</p>
            {isAdded && (
              <p className="text-slate-500 text-[11px]">
                This file was newly added in the published package and does not exist in the source repository.
              </p>
            )}
            {isRemoved && (
              <p className="text-slate-500 text-[11px]">
                This file was deleted in the published package.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
