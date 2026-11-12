import test from "node:test";
import assert from "node:assert/strict";
import { React, rtl, loadTsModule } from "./dom_setup.mjs";

const { render, screen, fireEvent, cleanup } = rtl;
const { Sidebar } = loadTsModule("src/components/Sidebar.tsx");
const { TopHeader } = loadTsModule("src/components/TopHeader.tsx");

test("Sidebar: renders branding, navigation items, badges, and system status telemetry", () => {
  cleanup();
  let selectedTab = null;

  render(
    React.createElement(Sidebar, {
      activeTab: "overview",
      setActiveTab: (tab) => {
        selectedTab = tab;
      },
      hasActiveReport: true,
      historyCount: 5,
      watchlistCount: 3,
      backendOnline: true,
      ollamaOnline: true,
    })
  );

  // Branding
  assert.ok(screen.getByText("VERITOR"));
  assert.ok(screen.getByText("Supply-Chain Security"));
  assert.ok(screen.getByText(/Verify Before You Trust/));

  // Navigation Items
  assert.ok(screen.getByText("Overview"));
  assert.ok(screen.getByText("Package Scanner"));
  assert.ok(screen.getByText("Investigation"));
  assert.ok(screen.getByText("Scan History"));
  assert.ok(screen.getByText("Watchlist"));
  assert.ok(screen.getByText("Settings"));

  // Badges (Investigation badge & Ollama status both say ACTIVE)
  const activeElements = screen.getAllByText("ACTIVE");
  assert.ok(activeElements.length >= 1);
  assert.ok(screen.getByText("5"));
  assert.ok(screen.getByText("3"));

  // Engine telemetry status
  assert.ok(screen.getByText("ONLINE"));
  assert.ok(screen.getByText("v0.1.0"));
  assert.ok(screen.getByText("Zero-Exec"));

  // Click navigation item
  fireEvent.click(screen.getByText("Package Scanner"));
  assert.equal(selectedTab, "scanner");
});

test("TopHeader: displays breadcrumbs, live status pills, and handles mobile menu trigger", () => {
  cleanup();
  let mobileMenuToggled = false;
  let quickScanTriggered = false;

  render(
    React.createElement(TopHeader, {
      activeTab: "history",
      setActiveTab: (tab) => {
        if (tab === "scanner") quickScanTriggered = true;
      },
      scanReport: null,
      backendOnline: true,
      ollamaOnline: false,
      onToggleMobileMenu: () => {
        mobileMenuToggled = true;
      },
    })
  );

  // Breadcrumbs
  assert.ok(screen.getByText("Veritor Console"));
  assert.ok(screen.getByText("Scan Audit History"));

  // Quick Action
  const newScanBtn = screen.getByRole("button", { name: /New Scan/i });
  assert.ok(newScanBtn);
  fireEvent.click(newScanBtn);
  assert.equal(quickScanTriggered, true);

  // Mobile menu button
  const mobileToggle = screen.getByTitle("Toggle Navigation Menu");
  assert.ok(mobileToggle);
  fireEvent.click(mobileToggle);
  assert.equal(mobileMenuToggled, true);
});
