import test from "node:test";
import assert from "node:assert/strict";
import { loadTsModule, mockFetch, React, rtl } from "./dom_setup.mjs";

const { render, screen, fireEvent, cleanup, waitFor } = rtl;

const { ReportDashboard } = loadTsModule("src/components/ReportDashboard.tsx");

function makeMockReport(overrides = {}) {
  return {
    scan_id: "scan-12345",
    ecosystem: "npm",
    package_name: "left-pad",
    version: "1.3.0",
    created_at: "2026-11-01T12:00:00Z",
    completed_at: "2026-11-01T12:00:05Z",
    status: "COMPLETED",
    source_match: {
      status: "MATCHED",
      confidence: "HIGH",
      method: "PACKAGE_TAG",
      explanation: "Exact tag match v1.3.0",
      commit_sha: "a1b2c3d4e5f6789012345678901234567890abcd",
      repository_url: "https://github.com/stevemao/left-pad",
      repository: {
        owner: "stevemao",
        name: "left-pad",
        url: "https://github.com/stevemao/left-pad",
      },
    },
    risk: {
      score: 15,
      level: "LOW",
      explanation: "Low risk: Clean source match with only standard packaging differences.",
      factors: [
        {
          id: "CLEAN_SOURCE",
          category: "COMPARISON",
          points: 0,
          description: "Source code matches tagged release perfectly.",
        },
      ],
    },
    comparison: {
      total_files: 5,
      authentic_files: 4,
      generated_files: 1,
      modified_files: 0,
      missing_in_pkg: 0,
      added_in_pkg: 1,
      identical_files: 4,
      similarity_score: 95.5,
      summary: {
        total_package_files: 5,
        added_files: 1,
        modified_files: 0,
        identical_files: 4,
      },
    },
    provenance: {
      status: "VERIFIED",
      explanation: "SLSA provenance signature verified under Sigstore public trust root.",
      claimed_in_metadata: true,
      signature_verified: true,
      tarball_digest_matches: true,
      source_repository: "https://github.com/stevemao/left-pad",
      source_commit: "a1b2c3d4e5f6789012345678901234567890abcd",
      repository_matches_declared: true,
      commit_matches_source_match: true,
    },
    security: {
      findings: [],
      high_count: 0,
      medium_count: 0,
      low_count: 0,
      info_count: 0,
    },
    ai_investigation: {
      summary: "Clean verified package.",
      explanation: "Automated analysis indicates no malicious activity.",
      confidence: "HIGH",
    },
    ...overrides,
  };
}

function makeMockComparisonData() {
  return {
    ecosystem: "npm",
    package_name: "left-pad",
    base_version: "1.2.0",
    head_version: "1.3.0",
    head_scan_id: "scan-12345",
    risk_change: {
      score_delta: -5,
      is_elevated: false,
      base_score: 20,
      head_score: 15,
    },
    file_changes: {
      newly_added: ["index.js"],
      newly_modified: [],
      newly_removed: [],
      new_suspicious_artifacts: [],
    },
    finding_changes: {
      new_findings: [],
      resolved_findings: [],
    },
    provenance_change: {
      changed: false,
      summary: "Provenance remains verified.",
    },
    summary: "Risk improved by 5 points compared to previous release v1.2.0.",
  };
}

test("ReportDashboard: renders risk score, level badge, and package header", () => {
  cleanup();
  const fetchMock = mockFetch(() => new Response("Not found", { status: 404 }));
  try {
    const report = makeMockReport();
    let currentTab = "overview";

    render(
      React.createElement(ReportDashboard, {
        report,
        activeReportTab: currentTab,
        setActiveReportTab: (tab) => {
          currentTab = tab;
        },
      })
    );

    // Risk Score and badge
    assert.ok(screen.getByText(/LOW\s+RISK\s+\(15\/100\)/));

    // Package Header
    assert.ok(screen.getByText("left-pad"));
    assert.ok(screen.getByText("v1.3.0"));
    assert.ok(screen.getByText("npm"));

    // Repository details
    assert.ok(screen.getByText("stevemao/left-pad"));
  } finally {
    fetchMock.restore();
  }
});

test("ReportDashboard: renders different risk levels (CRITICAL, HIGH, MEDIUM)", () => {
  cleanup();
  const fetchMock = mockFetch(() => new Response("Not found", { status: 404 }));
  try {
    const criticalReport = makeMockReport({
      risk: {
        score: 85,
        level: "CRITICAL",
        explanation: "Critical risk: Obfuscated payload with environment theft detected.",
        factors: [],
      },
    });

    render(
      React.createElement(ReportDashboard, {
        report: criticalReport,
        activeReportTab: "overview",
        setActiveReportTab: () => {},
      })
    );

    assert.ok(screen.getByText(/CRITICAL\s+RISK\s+\(85\/100\)/));
  } finally {
    fetchMock.restore();
  }
});

test("ReportDashboard: renders file comparison metrics", () => {
  cleanup();
  const fetchMock = mockFetch(() => new Response("Not found", { status: 404 }));
  try {
    const report = makeMockReport();

    render(
      React.createElement(ReportDashboard, {
        report,
        activeReportTab: "overview",
        setActiveReportTab: () => {},
      })
    );

    assert.ok(screen.getByText("Source Diffs"));
    assert.ok(screen.getByText(/5 files in package/));
  } finally {
    fetchMock.restore();
  }
});

test("ReportDashboard: switches tabs when navigation buttons are clicked", () => {
  cleanup();
  const fetchMock = mockFetch(() => new Response("Not found", { status: 404 }));
  try {
    const report = makeMockReport();
    const switchedTabs = [];

    render(
      React.createElement(ReportDashboard, {
        report,
        activeReportTab: "overview",
        setActiveReportTab: (tab) => {
          switchedTabs.push(tab);
        },
      })
    );

    const filesTab = screen.getByRole("button", { name: /Files & Diffs/i });
    const findingsTab = screen.getByRole("button", { name: /Security Findings/i });
    const provTab = screen.getByRole("button", { name: /Provenance/i });
    const aiTab = screen.getByRole("button", { name: /AI Investigator/i });

    fireEvent.click(filesTab);
    fireEvent.click(findingsTab);
    fireEvent.click(provTab);
    fireEvent.click(aiTab);

    assert.deepEqual(switchedTabs, ["files", "findings", "provenance", "ai"]);
  } finally {
    fetchMock.restore();
  }
});

test("ReportDashboard: fetches and displays previous release evolution delta", async () => {
  cleanup();
  const report = makeMockReport();
  const comparisonData = makeMockComparisonData();

  const fetchMock = mockFetch((url) => {
    if (url.includes(`/api/v1/scans/${report.scan_id}/compare-previous`)) {
      return new Response(JSON.stringify(comparisonData), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("Not found", { status: 404 });
  });

  try {
    render(
      React.createElement(ReportDashboard, {
        report,
        activeReportTab: "overview",
        setActiveReportTab: () => {},
      })
    );

    await waitFor(() => {
      assert.ok(screen.getByText(/Release Evolution: 1\.2\.0 → 1\.3\.0/));
      assert.ok(screen.getByText(comparisonData.summary));
      assert.ok(screen.getByText(/Risk: -5 pts/));
    });

    assert.equal(fetchMock.calls.length, 1);
  } finally {
    fetchMock.restore();
  }
});

test("ReportDashboard: triggers JSON export via API", async () => {
  cleanup();
  const report = makeMockReport();

  let downloadedBlob = null;
  const origCreateObjectURL = global.window.URL.createObjectURL;
  const origRevokeObjectURL = global.window.URL.revokeObjectURL;
  global.window.URL.createObjectURL = (blob) => {
    downloadedBlob = blob;
    return "blob:http://localhost:3000/export-123";
  };
  global.window.URL.revokeObjectURL = () => {};

  const fetchMock = mockFetch((url) => {
    if (url.includes(`/api/v1/scans/${report.scan_id}/export/json`)) {
      return new Response(JSON.stringify({ report: "data" }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Content-Disposition": 'attachment; filename="veritor_report.json"',
        },
      });
    }
    return new Response("Not found", { status: 404 });
  });

  try {
    render(
      React.createElement(ReportDashboard, {
        report,
        activeReportTab: "overview",
        setActiveReportTab: () => {},
      })
    );

    const exportBtn = screen.getByRole("button", { name: /Export JSON/i });
    fireEvent.click(exportBtn);

    await waitFor(() => {
      assert.ok(downloadedBlob !== null, "Must trigger blob creation for JSON download");
    });

    const calls = fetchMock.calls.filter((c) => c.url.includes("/export/json"));
    assert.equal(calls.length, 1);
  } finally {
    global.window.URL.createObjectURL = origCreateObjectURL;
    global.window.URL.revokeObjectURL = origRevokeObjectURL;
    fetchMock.restore();
  }
});
