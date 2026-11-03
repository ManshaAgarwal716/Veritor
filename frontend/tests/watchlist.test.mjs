import test from "node:test";
import assert from "node:assert/strict";
import { loadTsModule, mockFetch, React, rtl } from "./dom_setup.mjs";

const { render, screen, fireEvent, cleanup, waitFor } = rtl;

const { WatchlistView } = loadTsModule("src/components/WatchlistView.tsx");
const storage = loadTsModule("src/lib/storage.ts");

test("WatchlistView: renders empty state when watchlist is empty", () => {
  cleanup();
  render(
    React.createElement(WatchlistView, {
      watchlist: [],
      onTriggerScan: () => {},
      onRefresh: () => {},
    })
  );

  assert.ok(screen.getByText("Package Watchlist & Release Monitor"));
  assert.ok(screen.getByText("(0 monitored)"));
  assert.ok(screen.getByText("Watchlist is Empty"));
  assert.ok(
    screen.getByText(
      /Add critical upstream dependencies to monitor new releases/
    )
  );

  const checkBtn = screen.getByRole("button", { name: /Check for Updates/i });
  assert.equal(checkBtn.disabled, true, "Check button should be disabled when empty");
});

test("WatchlistView: renders table with monitored packages and update badges", () => {
  cleanup();
  let scannedPackage = null;
  const mockWatchlist = [
    {
      id: "npm:express",
      ecosystem: "npm",
      package_name: "express",
      last_scanned_version: "4.18.2",
      latest_version: "4.19.0",
      has_update: true,
      last_risk_score: 15,
      last_risk_level: "LOW",
      notes: "Core API server",
    },
    {
      id: "pypi:requests",
      ecosystem: "pypi",
      package_name: "requests",
      last_scanned_version: "2.31.0",
      latest_version: "2.31.0",
      has_update: false,
      last_risk_score: 0,
      last_risk_level: "LOW",
    },
  ];

  render(
    React.createElement(WatchlistView, {
      watchlist: mockWatchlist,
      onTriggerScan: (eco, pkg, ver) => {
        scannedPackage = { eco, pkg, ver };
      },
      onRefresh: () => {},
    })
  );

  assert.ok(screen.getByText("(2 monitored)"));
  assert.ok(screen.getByText("express"));
  assert.ok(screen.getByText("Core API server"));
  assert.ok(screen.getByText("v4.18.2"));
  assert.ok(screen.getByText(/v4.19.0 \(Update\)/));

  assert.ok(screen.getByText("requests"));
  assert.ok(screen.getByText(/v2.31.0 \(Latest\)/));

  // Trigger scan button for express (should pass latest_version because has_update is true)
  const scanButtons = screen.getAllByRole("button", { name: /Scan/i });
  fireEvent.click(scanButtons[0]);

  assert.deepEqual(scannedPackage, {
    eco: "npm",
    pkg: "express",
    ver: "4.19.0",
  });
});

test("WatchlistView: validates package name input on add", async () => {
  cleanup();
  render(
    React.createElement(WatchlistView, {
      watchlist: [],
      onTriggerScan: () => {},
      onRefresh: () => {},
    })
  );

  const addBtn = screen.getByRole("button", { name: /Add Watch/i });
  const form = addBtn.closest("form");
  fireEvent.submit(form);

  assert.ok(screen.getByText("Package name cannot be empty."));
});

test("WatchlistView: adds a package and triggers onRefresh", async () => {
  cleanup();
  let refreshed = false;
  const fetchMock = mockFetch((url, method, init) => {
    if (url.endsWith("/api/v1/watchlist") && method === "POST") {
      const body = JSON.parse(init.body);
      return new Response(
        JSON.stringify({
          id: `${body.ecosystem}:${body.package_name}`,
          ...body,
          created_at: new Date().toISOString(),
        }),
        { status: 201, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response("Not found", { status: 404 });
  });

  try {
    render(
      React.createElement(WatchlistView, {
        watchlist: [],
        onTriggerScan: () => {},
        onRefresh: () => {
          refreshed = true;
        },
      })
    );

    const input = screen.getByPlaceholderText("Package name (e.g. lodash, requests)");
    fireEvent.change(input, { target: { value: "lodash" } });

    const form = input.closest("form");
    fireEvent.submit(form);

    await waitFor(() => {
      assert.equal(refreshed, true, "Must call onRefresh after adding package");
    });

    assert.equal(fetchMock.calls.length, 1);
    assert.equal(fetchMock.calls[0].method, "POST");
    assert.ok(fetchMock.calls[0].url.endsWith("/api/v1/watchlist"));
  } finally {
    fetchMock.restore();
  }
});

test("WatchlistView: removes a package and triggers onRefresh", async () => {
  cleanup();
  let refreshed = false;
  const fetchMock = mockFetch((url, method) => {
    if (url.includes("/api/v1/watchlist/npm%3Aexpress") && method === "DELETE") {
      return new Response(JSON.stringify({ ok: true, deleted: "npm:express" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("Not found", { status: 404 });
  });

  try {
    render(
      React.createElement(WatchlistView, {
        watchlist: [
          {
            id: "npm:express",
            ecosystem: "npm",
            package_name: "express",
          },
        ],
        onTriggerScan: () => {},
        onRefresh: () => {
          refreshed = true;
        },
      })
    );

    const removeBtn = screen.getByTitle("Remove from watchlist");
    fireEvent.click(removeBtn);

    await waitFor(() => {
      assert.equal(refreshed, true, "Must call onRefresh after deleting package");
    });

    assert.equal(fetchMock.calls.length, 1);
    assert.equal(fetchMock.calls[0].method, "DELETE");
  } finally {
    fetchMock.restore();
  }
});

test("WatchlistView: handles update checking state and display message", async () => {
  cleanup();
  let refreshed = false;
  const fetchMock = mockFetch((url, method) => {
    if (url.endsWith("/api/v1/watchlist/check") && method === "POST") {
      return new Response(
        JSON.stringify({
          checked_count: 3,
          updates_detected: 1,
          scans_triggered: 1,
          results: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response("Not found", { status: 404 });
  });

  try {
    render(
      React.createElement(WatchlistView, {
        watchlist: [
          {
            id: "npm:express",
            ecosystem: "npm",
            package_name: "express",
          },
        ],
        onTriggerScan: () => {},
        onRefresh: () => {
          refreshed = true;
        },
      })
    );

    const checkBtn = screen.getByRole("button", { name: /Check for Updates/i });
    fireEvent.click(checkBtn);

    await waitFor(() => {
      assert.ok(
        screen.getByText(
          /Checked 3 packages: 1 update\(s\) detected, 1 scan\(s\) triggered\./
        )
      );
    });

    assert.equal(refreshed, true);
  } finally {
    fetchMock.restore();
  }
});

test("WatchlistView: displays error message when checking updates fails", async () => {
  cleanup();
  const fetchMock = mockFetch(() => {
    return new Response(JSON.stringify({ detail: "Registry rate limit reached" }), {
      status: 429,
      headers: { "Content-Type": "application/json" },
    });
  });

  try {
    render(
      React.createElement(WatchlistView, {
        watchlist: [
          {
            id: "npm:express",
            ecosystem: "npm",
            package_name: "express",
          },
        ],
        onTriggerScan: () => {},
        onRefresh: () => {},
      })
    );

    const checkBtn = screen.getByRole("button", { name: /Check for Updates/i });
    fireEvent.click(checkBtn);

    await waitFor(() => {
      assert.ok(screen.getByText(/Check failed: ApiError: Registry rate limit reached/));
    });
  } finally {
    fetchMock.restore();
  }
});

test("storage syncWatchlist: synchronizes with backend and updates localStorage fallback", async () => {
  global.localStorage.clear();

  const mockItems = [
    {
      id: "npm:lodash",
      ecosystem: "npm",
      package_name: "lodash",
      created_at: "2026-11-01T00:00:00Z",
    },
  ];

  const fetchMock = mockFetch((url, method) => {
    if (url.endsWith("/api/v1/watchlist") && method === "GET") {
      return new Response(JSON.stringify(mockItems), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("Not found", { status: 404 });
  });

  try {
    const synced = await storage.syncWatchlist();
    assert.deepEqual(synced, mockItems);

    // Verify localStorage fallback cache was updated
    const cached = JSON.parse(global.localStorage.getItem("veritor_watchlist_v1") || "[]");
    assert.deepEqual(cached, mockItems);
  } finally {
    fetchMock.restore();
  }
});

test("storage syncWatchlist: falls back to localStorage when backend API is unreachable", async () => {
  global.localStorage.clear();
  const offlineItem = {
    id: "npm:express",
    ecosystem: "npm",
    package_name: "express",
    created_at: "2026-11-01T00:00:00Z",
  };
  global.localStorage.setItem("veritor_watchlist_v1", JSON.stringify([offlineItem]));

  const fetchMock = mockFetch(() => {
    throw new Error("Network connection refused");
  });

  try {
    const result = await storage.syncWatchlist();
    assert.deepEqual(result, [offlineItem], "Must return cached localStorage items on network failure");
  } finally {
    fetchMock.restore();
  }
});
