import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const rootDir = path.resolve(__dirname, "..");
export const srcDir = path.join(rootDir, "src");

// 1. Initialize JSDOM immediately so global window & document exist before testing-library loads
export const dom = new JSDOM("<!DOCTYPE html><html><body><div id=\"root\"></div></body></html>", {
  url: "http://localhost:3000",
  pretendToBeVisual: true,
});

global.window = dom.window;
global.document = dom.window.document;
Object.defineProperty(globalThis, "navigator", {
  value: dom.window.navigator,
  writable: true,
  configurable: true,
});
global.HTMLElement = dom.window.HTMLElement;
global.HTMLInputElement = dom.window.HTMLInputElement;
global.HTMLButtonElement = dom.window.HTMLButtonElement;
global.HTMLAnchorElement = dom.window.HTMLAnchorElement;
global.HTMLAnchorElement.prototype.click = function () {};
global.HTMLSelectElement = dom.window.HTMLSelectElement;
global.HTMLTableElement = dom.window.HTMLTableElement;
global.Event = dom.window.Event;
global.CustomEvent = dom.window.CustomEvent;
global.MouseEvent = dom.window.MouseEvent;
global.KeyboardEvent = dom.window.KeyboardEvent;
global.localStorage = dom.window.localStorage;
global.Blob = dom.window.Blob;

// 2. Now import React and Testing Library with document established
const React = require("react");
const ts = require("typescript");
const rtl = require("@testing-library/react");

const moduleCache = {};

export function loadTsModule(relPath) {
  const fullPath = path.isAbsolute(relPath) ? relPath : path.resolve(rootDir, relPath);
  if (moduleCache[fullPath]) return moduleCache[fullPath].exports;

  const code = fs.readFileSync(fullPath, "utf8");
  const transpiled = ts.transpileModule(code, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  });

  const customRequire = (reqPath) => {
    if (reqPath.startsWith(".")) {
      const dir = path.dirname(fullPath);
      let target = path.resolve(dir, reqPath);
      if (fs.existsSync(target + ".ts")) target += ".ts";
      else if (fs.existsSync(target + ".tsx")) target += ".tsx";
      else if (fs.existsSync(target + ".js")) target += ".js";
      return loadTsModule(target);
    }
    return require(reqPath);
  };

  const m = { exports: {} };
  moduleCache[fullPath] = m;
  const fn = new Function("require", "module", "exports", transpiled.outputText);
  fn(customRequire, m, m.exports);
  return m.exports;
}

export function mockFetch(handler) {
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = init.method || "GET";
    calls.push({ url, method, init });
    return handler(url, method, init);
  };
  return {
    calls,
    restore() {
      global.fetch = originalFetch;
    },
  };
}

export { React, rtl };
