import test from "node:test";
import assert from "node:assert/strict";
import { React, rtl, loadTsModule } from "./dom_setup.mjs";

const { render, screen, fireEvent, cleanup } = rtl;
const { ProgressTracker } = loadTsModule("src/components/ProgressTracker.tsx");

test("ProgressTracker: renders in-progress state with stage indicator and progress percentage", () => {
  cleanup();

  const mockStatus = {
    scan_id: "scan-test-123",
    ecosystem: "npm",
    package_name: "left-pad",
    version: "1.3.0",
    stage: "comparing",
    status: "in_progress",
    progress_percent: 65,
    message: "Comparing package tarball against source tree...",
  };

  render(
    React.createElement(ProgressTracker, {
      status: mockStatus,
    })
  );

  assert.ok(screen.getByText("left-pad@1.3.0"));
  assert.ok(screen.getByText("scan-test-123"));
  assert.ok(screen.getByText("65%"));
  assert.ok(screen.getByText("Comparing package tarball against source tree..."));
  assert.ok(screen.getByText("ANALYZING"));
  assert.ok(screen.getByText("Differential Engine"));
});

test("ProgressTracker: renders completed state with verification badge", () => {
  cleanup();

  const mockStatus = {
    scan_id: "scan-completed-456",
    ecosystem: "pypi",
    package_name: "requests",
    version: "2.31.0",
    stage: "completed",
    status: "completed",
    progress_percent: 100,
    message: "Package integrity verification complete.",
  };

  render(
    React.createElement(ProgressTracker, {
      status: mockStatus,
    })
  );

  assert.ok(screen.getByText("requests@2.31.0"));
  assert.ok(screen.getByText("COMPLETED"));
  assert.ok(screen.getByText("100%"));
});

test("ProgressTracker: renders failed state and triggers onRetry callback", () => {
  cleanup();
  let retried = false;

  const mockStatus = {
    scan_id: "scan-failed-789",
    ecosystem: "npm",
    package_name: "non-existent-pkg",
    version: "0.0.1",
    stage: "resolving_source",
    status: "failed",
    progress_percent: 30,
    error: "Repository could not be located in registry metadata.",
  };

  render(
    React.createElement(ProgressTracker, {
      status: mockStatus,
      onRetry: () => {
        retried = true;
      },
    })
  );

  assert.ok(screen.getByText("FAILED"));
  assert.ok(screen.getByText("Analysis Interrupted"));
  assert.ok(screen.getByText("Repository could not be located in registry metadata."));

  const retryBtn = screen.getByRole("button", { name: /Retry Scan/i });
  assert.ok(retryBtn);
  fireEvent.click(retryBtn);
  assert.equal(retried, true);
});
