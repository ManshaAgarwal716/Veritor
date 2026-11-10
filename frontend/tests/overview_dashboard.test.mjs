import test from "node:test";
import assert from "node:assert/strict";
import { React, rtl, loadTsModule } from "./dom_setup.mjs";

const { render, screen, fireEvent, cleanup } = rtl;
const { OverviewDashboard } = loadTsModule("src/components/OverviewDashboard.tsx");

const mockHistory = [
  {
    scan_id: "scan-1",
    ecosystem: "npm",
    package_name: "chalk",
    version: "5.3.0",
    status: "completed",
    risk_score: 15,
    risk_level: "LOW",
    timestamp: "2026-11-04T12:00:00Z",
  },
  {
    scan_id: "scan-2",
    ecosystem: "npm",
    package_name: "event-stream",
    version: "3.3.6",
    status: "completed",
    risk_score: 85,
    risk_level: "CRITICAL",
    timestamp: "2026-11-04T13:00:00Z",
  },
];

const mockWatchlist = [
  {
    id: "watch-1",
    ecosystem: "npm",
    package_name: "express",
    notes: "Core API",
    latest_version: "4.19.2",
    has_update: false,
    created_at: "2026-11-04T10:00:00Z",
  },
];

test("OverviewDashboard: renders metrics computed from actual scan history and watchlist", () => {
  cleanup();
  render(
    React.createElement(OverviewDashboard, {
      history: mockHistory,
      watchlist: mockWatchlist,
      onStartScan: () => {},
      onOpenReport: () => {},
      onNavigateToScanner: () => {},
      onNavigateToWatchlist: () => {},
    })
  );

  // Total scans: 2
  assert.ok(screen.getByText("Total Package Scans"));
  const twos = screen.getAllByText("2");
  assert.ok(twos.length >= 1);

  // Critical/High Alerts: 1 (event-stream)
  assert.ok(screen.getByText("Critical / High Alerts"));
  const ones = screen.getAllByText("1");
  assert.ok(ones.length >= 1);

  // Monitored watchlist: 1
  assert.ok(screen.getByText("Watchlist Monitored"));
});

test("OverviewDashboard: renders empty state when no scan history exists", () => {
  cleanup();
  let navigatedToScanner = false;

  render(
    React.createElement(OverviewDashboard, {
      history: [],
      watchlist: [],
      onStartScan: () => {},
      onOpenReport: () => {},
      onNavigateToScanner: () => {
        navigatedToScanner = true;
      },
      onNavigateToWatchlist: () => {},
    })
  );

  assert.ok(screen.getByText("No Security Scans Recorded Yet"));
  const launchBtn = screen.getByRole("button", { name: /Launch First Scan/i });
  assert.ok(launchBtn);
  fireEvent.click(launchBtn);
  assert.equal(navigatedToScanner, true);
});

test("OverviewDashboard: renders recent scan activity table and triggers report inspection", () => {
  cleanup();
  let inspectedItem = null;

  render(
    React.createElement(OverviewDashboard, {
      history: mockHistory,
      watchlist: mockWatchlist,
      onStartScan: () => {},
      onOpenReport: (item) => {
        inspectedItem = item;
      },
      onNavigateToScanner: () => {},
      onNavigateToWatchlist: () => {},
    })
  );

  assert.ok(screen.getAllByText("chalk").length >= 1);
  assert.ok(screen.getAllByText("event-stream").length >= 1);

  const inspectButtons = screen.getAllByRole("button", { name: /Inspect/i });
  assert.ok(inspectButtons.length >= 2);
  fireEvent.click(inspectButtons[0]);
  assert.ok(inspectedItem);
  assert.equal(inspectedItem.package_name, "chalk");
});

test("OverviewDashboard: validates and triggers quick package verification", () => {
  cleanup();
  let scanParams = null;

  render(
    React.createElement(OverviewDashboard, {
      history: mockHistory,
      watchlist: mockWatchlist,
      onStartScan: (ecosystem, name, version) => {
        scanParams = { ecosystem, name, version };
      },
      onOpenReport: () => {},
      onNavigateToScanner: () => {},
      onNavigateToWatchlist: () => {},
    })
  );

  const verifyBtn = screen.getByRole("button", { name: /Verify/i });

  // 1. Click without inputs -> validation error
  fireEvent.click(verifyBtn);
  assert.ok(screen.getByText("Package name is required."));

  // 2. Fill package name and version
  const pkgInput = screen.getByPlaceholderText("e.g. left-pad, express");
  const verInput = screen.getByPlaceholderText("1.3.0");

  fireEvent.change(pkgInput, { target: { value: "left-pad" } });
  fireEvent.change(verInput, { target: { value: "1.3.0" } });
  fireEvent.click(verifyBtn);

  assert.ok(scanParams);
  assert.equal(scanParams.ecosystem, "npm");
  assert.equal(scanParams.name, "left-pad");
  assert.equal(scanParams.version, "1.3.0");
});
