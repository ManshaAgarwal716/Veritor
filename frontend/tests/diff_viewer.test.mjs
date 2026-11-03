import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import React from "react";
import ReactDOMServer from "react-dom/server";

const require = createRequire(import.meta.url);

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");
const diffViewerPath = path.join(rootDir, "src", "components", "DiffViewer.tsx");

// Transpile DiffViewer.tsx on the fly for component testing
const tsxSource = fs.readFileSync(diffViewerPath, "utf8");
const transpiled = ts.transpileModule(tsxSource, {
  compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
});

const moduleObj = { exports: {} };
const runner = new Function("require", "module", "exports", transpiled.outputText);
runner(
  (id) => {
    if (id === "react") return React;
    if (id === "react/jsx-runtime") {
      // Provide jsx-runtime
      const jsxRuntime = require("react/jsx-runtime");
      return jsxRuntime;
    }
    return require(id);
  },
  moduleObj,
  moduleObj.exports
);

const { DiffViewer, parseUnifiedDiff, highlightTokens } = moduleObj.exports;

test("DiffViewer renders loading state when isLoading is true", () => {
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(DiffViewer, {
      diff: null,
      isLoading: true,
      filePath: "src/utils.ts",
    })
  );
  assert.ok(html.includes('data-testid="diff-viewer-loading"'), "Must render loading container");
  assert.ok(html.includes("Loading diff for src/utils.ts..."), "Must show loading label with path");
});

test("DiffViewer renders empty state when diff is null", () => {
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(DiffViewer, {
      diff: null,
      isLoading: false,
      filePath: "",
    })
  );
  assert.ok(html.includes('data-testid="diff-viewer-empty"'), "Must render empty container");
  assert.ok(
    html.includes("Select a file from the explorer to view differences"),
    "Must prompt user to select a file"
  );
});

test("DiffViewer renders identical file state when diff_status is CLEAN", () => {
  const diff = {
    path: "src/core.py",
    status: "IDENTICAL",
    diff_status: "CLEAN",
    unified: null,
  };
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(DiffViewer, {
      diff,
      isLoading: false,
      filePath: "src/core.py",
    })
  );
  assert.ok(html.includes('data-testid="diff-identical"'), "Must render identical view");
  assert.ok(
    html.includes("File is identical between source repository and published package"),
    "Must state files are identical"
  );
});

test("DiffViewer renders binary file message when diff_status is BINARY", () => {
  const diff = {
    path: "assets/logo.png",
    status: "MODIFIED",
    diff_status: "BINARY",
    unified: null,
  };
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(DiffViewer, {
      diff,
      isLoading: false,
      filePath: "assets/logo.png",
    })
  );
  assert.ok(html.includes('data-testid="diff-binary"'), "Must render binary view");
  assert.ok(
    html.includes("Binary file (diff cannot be displayed in text view)"),
    "Must explain that binary diffs cannot be shown as text"
  );
});

test("DiffViewer renders added file with missing source indicator", () => {
  const diff = {
    path: "injected.js",
    status: "ADDED",
    diff_status: "DIFF",
    classification: "SUSPICIOUS",
    added_lines: 3,
    removed_lines: 0,
    unified: "--- /dev/null\n+++ b/injected.js\n@@ -0,0 +1,3 @@\n+const x = 1;\n+const y = 2;\n+export default x;",
  };
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(DiffViewer, {
      diff,
      isLoading: false,
      filePath: "injected.js",
      initialViewMode: "split",
    })
  );
  assert.ok(html.includes("Missing in Source"), "Must display Missing in Source badge");
  assert.ok(html.includes("File Absent"), "Split view must indicate file is absent from source");
  assert.ok(html.includes("SUSPICIOUS"), "Must display artifact classification");
  assert.ok(html.includes("+3"), "Must display added lines count");
});

test("DiffViewer renders removed file with removed in package indicator", () => {
  const diff = {
    path: "legacy.js",
    status: "REMOVED",
    diff_status: "DIFF",
    added_lines: 0,
    removed_lines: 2,
    unified: "--- a/legacy.js\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-const old = true;\n-export default old;",
  };
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(DiffViewer, {
      diff,
      isLoading: false,
      filePath: "legacy.js",
      initialViewMode: "split",
    })
  );
  assert.ok(html.includes("Removed in Package"), "Must display Removed in Package badge");
  assert.ok(html.includes("File Removed"), "Split view must indicate file was removed in package");
  assert.ok(html.includes("-2"), "Must display removed lines count");
});

test("DiffViewer renders unified diff mode with line numbers and toggle controls", () => {
  const diff = {
    path: "src/server.js",
    status: "MODIFIED",
    diff_status: "DIFF",
    added_lines: 2,
    removed_lines: 1,
    unified: [
      "--- a/src/server.js",
      "+++ b/src/server.js",
      "@@ -10,3 +10,4 @@ function start() {",
      "   const host = 'localhost';",
      "-  const port = 3000;",
      "+  const port = process.env.PORT || 8080;",
      "+  const debug = false;",
      "   return { host, port };",
    ].join("\n"),
  };

  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(DiffViewer, {
      diff,
      isLoading: false,
      filePath: "src/server.js",
      initialViewMode: "unified",
    })
  );

  assert.ok(html.includes('data-testid="unified-diff-table"'), "Must render unified diff table");
  assert.ok(html.includes('data-testid="toggle-unified"'), "Must include toggle unified button");
  assert.ok(html.includes('data-testid="toggle-split"'), "Must include toggle split button");

  // Old and new line numbers
  assert.ok(html.includes(">10<"), "Must render line number 10");
  assert.ok(html.includes(">11<"), "Must render line number 11");

  // Code contents and syntax tokens
  assert.ok(html.includes("localhost"), "Must contain code content");
  assert.ok(html.includes("text-purple-400"), "Must render keyword syntax highlight class");
  assert.ok(html.includes("text-emerald-300"), "Must render string syntax highlight class");
});

test("DiffViewer renders side-by-side (split) mode with aligned modified lines", () => {
  const diff = {
    path: "src/calc.py",
    status: "MODIFIED",
    diff_status: "DIFF",
    added_lines: 2,
    removed_lines: 1,
    unified: [
      "--- a/src/calc.py",
      "+++ b/src/calc.py",
      "@@ -5,3 +5,4 @@",
      " def compute(val):",
      "-    return val * 10",
      "+    factor = 20",
      "+    return val * factor",
      " # end compute",
    ].join("\n"),
  };

  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(DiffViewer, {
      diff,
      isLoading: false,
      filePath: "src/calc.py",
      initialViewMode: "split",
    })
  );

  assert.ok(html.includes('data-testid="split-diff-view"'), "Must render split diff view container");
  assert.ok(html.includes('data-testid="split-diff-table"'), "Must render split diff table");
  assert.ok(html.includes("Source Repository (Original)"), "Must render left header pane");
  assert.ok(html.includes("Published Package (Artifact)"), "Must render right header pane");

  // Left pane deletion aligned with right pane addition
  assert.ok(html.includes("return"), "Must contain return keyword");
  assert.ok(html.includes("val"), "Must contain variable val");
  assert.ok(html.includes("10"), "Must contain deleted code in left pane");
  assert.ok(html.includes("factor"), "Must contain added code in right pane");
  assert.ok(html.includes("20"), "Must contain added factor value in right pane");
});

test("parseUnifiedDiff aligns modified lines and preserves line numbers", () => {
  const raw = [
    "--- a/test.ts",
    "+++ b/test.ts",
    "@@ -20,4 +20,5 @@",
    " const a = 1;",
    "-const b = 2;",
    "-const c = 3;",
    "+const b = 20;",
    "+const c = 30;",
    "+const d = 40;",
    " const e = 5;",
  ].join("\n");

  const { unifiedRows, splitRows } = parseUnifiedDiff(raw);

  assert.equal(unifiedRows.length, 10, "Must produce 10 unified rows (2 info + 1 header + 7 data)");
  assert.equal(splitRows.length, 6, "Must produce 6 split rows (1 header + 5 aligned rows)");

  // Split row 0: header
  assert.equal(splitRows[0].type, "header");

  // Split row 1: context line 20
  assert.equal(splitRows[1].left.lineNumber, 20);
  assert.equal(splitRows[1].right.lineNumber, 20);

  // Split row 2: modified line (deletion of b=2 aligned with addition of b=20)
  assert.equal(splitRows[2].left.lineNumber, 21);
  assert.equal(splitRows[2].left.type, "deletion");
  assert.equal(splitRows[2].right.lineNumber, 21);
  assert.equal(splitRows[2].right.type, "addition");

  // Split row 3: modified line (deletion of c=3 aligned with addition of c=30)
  assert.equal(splitRows[3].left.lineNumber, 22);
  assert.equal(splitRows[3].left.type, "deletion");
  assert.equal(splitRows[3].right.lineNumber, 22);
  assert.equal(splitRows[3].right.type, "addition");

  // Split row 4: addition only (d=40 on right, empty on left)
  assert.equal(splitRows[4].left.type, "empty");
  assert.equal(splitRows[4].right.lineNumber, 23);
  assert.equal(splitRows[4].right.type, "addition");

  // Split row 5: context line 23 on left, 24 on right
  assert.equal(splitRows[5].left.lineNumber, 23);
  assert.equal(splitRows[5].right.lineNumber, 24);
});

test("highlightTokens correctly tags keywords, strings, comments, numbers, and literals", () => {
  const line = 'const maxCount = 100; const msg = "test string"; const active = true; // maximum attempts';
  const highlighted = highlightTokens(line);
  assert.ok(Array.isArray(highlighted), "Should return array of React elements");

  // Render to string and verify classes
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement("span", null, ...highlighted)
  );
  assert.ok(html.includes("text-purple-400"), "Keyword 'const' must receive purple styling");
  assert.ok(html.includes("text-amber-400"), "Number '100' must receive amber styling");
  assert.ok(html.includes("text-slate-500"), "Comment '// maximum attempts' must receive slate styling");
  assert.ok(html.includes("text-emerald-300"), "String '\"test string\"' must receive emerald styling");
  assert.ok(html.includes("text-cyan-400"), "Boolean 'true' must receive cyan styling");
});
