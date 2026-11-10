import test from "node:test";
import assert from "node:assert/strict";
import { loadTsModule, mockFetch } from "./dom_setup.mjs";

const api = loadTsModule("src/lib/api.ts");

test("ApiError: initializes with message, status, and details", () => {
  const err = new api.ApiError("Resource not found", 404, { id: "scan-123" });
  assert.equal(err.name, "ApiError");
  assert.equal(err.message, "Resource not found");
  assert.equal(err.status, 404);
  assert.deepEqual(err.details, { id: "scan-123" });
  assert.ok(err instanceof Error);
});

test("getApiBaseUrl & setApiBaseUrl: manages localStorage and default fallback", () => {
  localStorage.removeItem("veritor_api_base_url");
  const defaultUrl = api.getApiBaseUrl();
  assert.ok(defaultUrl.length > 0);
  assert.ok(!defaultUrl.endsWith("/"));

  api.setApiBaseUrl("http://custom-host:9000/");
  assert.equal(api.getApiBaseUrl(), "http://custom-host:9000");

  api.setApiBaseUrl("");
  assert.equal(api.getApiBaseUrl(), defaultUrl);
});

test("API error parsing: extracts 'detail' from JSON 400 responses", async () => {
  const fetchMock = mockFetch(async () => {
    return new Response(JSON.stringify({ detail: "Invalid semver range specified" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  });

  try {
    await assert.rejects(
      async () => {
        await api.createScan({ ecosystem: "npm", package_name: "test-pkg", version: "bad" });
      },
      (err) => {
        assert.ok(err instanceof api.ApiError);
        assert.equal(err.status, 400);
        assert.equal(err.message, "Invalid semver range specified");
        return true;
      }
    );
  } finally {
    fetchMock.restore();
  }
});

test("API error parsing: extracts error.message and error.details", async () => {
  const fetchMock = mockFetch(async () => {
    return new Response(
      JSON.stringify({
        error: {
          message: "Database connection failed",
          details: { retry_after: 5 },
        },
      }),
      {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }
    );
  });

  try {
    await assert.rejects(
      async () => {
        await api.getScanReport("scan-999");
      },
      (err) => {
        assert.ok(err instanceof api.ApiError);
        assert.equal(err.status, 503);
        assert.equal(err.message, "Database connection failed");
        assert.deepEqual(err.details, { retry_after: 5 });
        return true;
      }
    );
  } finally {
    fetchMock.restore();
  }
});

test("API error parsing: extracts fallback 'message' field", async () => {
  const fetchMock = mockFetch(async () => {
    return new Response(JSON.stringify({ message: "Authentication expired" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  });

  try {
    await assert.rejects(
      async () => {
        await api.getWatchlist();
      },
      (err) => {
        assert.ok(err instanceof api.ApiError);
        assert.equal(err.status, 401);
        assert.equal(err.message, "Authentication expired");
        return true;
      }
    );
  } finally {
    fetchMock.restore();
  }
});

test("API error parsing: handles non-JSON / plain text error responses", async () => {
  const fetchMock = mockFetch(async () => {
    return new Response("<html>Bad Gateway 502</html>", {
      status: 502,
      headers: { "Content-Type": "text/html" },
    });
  });

  try {
    await assert.rejects(
      async () => {
        await api.getScanStatus("scan-123");
      },
      (err) => {
        assert.ok(err instanceof api.ApiError);
        assert.equal(err.status, 502);
        assert.equal(err.message, "API request failed with status 502");
        return true;
      }
    );
  } finally {
    fetchMock.restore();
  }
});

test("createScan: sends POST with JSON body and returns scan response", async () => {
  const fetchMock = mockFetch(async (url, method, init) => {
    assert.ok(url.endsWith("/api/v1/scans"));
    assert.equal(method, "POST");
    const body = JSON.parse(init.body);
    assert.equal(body.ecosystem, "npm");
    assert.equal(body.package_name, "lodash");
    assert.equal(body.version, "4.17.21");

    return new Response(
      JSON.stringify({
        scan_id: "scan_abc123",
        status: "queued",
        ecosystem: "npm",
        package_name: "lodash",
        version: "4.17.21",
        created_at: "2026-11-03T00:00:00Z",
      }),
      { status: 202, headers: { "Content-Type": "application/json" } }
    );
  });

  try {
    const res = await api.createScan({
      ecosystem: "npm",
      package_name: "lodash",
      version: "4.17.21",
    });
    assert.equal(res.scan_id, "scan_abc123");
    assert.equal(res.status, "queued");
  } finally {
    fetchMock.restore();
  }
});

test("getFileDiff: preserves path separators while encoding path segments (BUG-03)", async () => {
  const fetchMock = mockFetch(async (url, method) => {
    assert.equal(method, "GET");
    // Verify that directory slashes are preserved, but special chars like '#' or ' ' are encoded
    assert.ok(url.includes("/api/v1/scans/scan%201/files/dist%20dir/special%23file.js/diff"));

    return new Response(
      JSON.stringify({
        file_path: "dist dir/special#file.js",
        status: "modified",
        classification: "code",
        diff: "@@ -1 +1 @@\n-old\n+new\n",
        similarity_score: 0.85,
        lines_added: 1,
        lines_removed: 1,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  });

  try {
    const diff = await api.getFileDiff("scan 1", "dist dir/special#file.js");
    assert.equal(diff.file_path, "dist dir/special#file.js");
    assert.equal(diff.lines_added, 1);
  } finally {
    fetchMock.restore();
  }
});

test("removeFromWatchlist: succeeds on 200/204, ignores 404, throws on 500", async () => {
  // Case 1: 200 OK
  let fetchMock = mockFetch(async () => new Response(null, { status: 200 }));
  try {
    await api.removeFromWatchlist("entry-1");
  } finally {
    fetchMock.restore();
  }

  // Case 2: 404 Not Found (should not throw per API contract)
  fetchMock = mockFetch(async () => new Response(null, { status: 404, statusText: "Not Found" }));
  try {
    await api.removeFromWatchlist("entry-missing");
  } finally {
    fetchMock.restore();
  }

  // Case 3: 500 Server Error (should throw ApiError)
  fetchMock = mockFetch(async () => new Response(null, { status: 500, statusText: "Server Error" }));
  try {
    await assert.rejects(
      async () => {
        await api.removeFromWatchlist("entry-err");
      },
      (err) => {
        assert.ok(err instanceof api.ApiError);
        assert.equal(err.status, 500);
        return true;
      }
    );
  } finally {
    fetchMock.restore();
  }
});

test("checkBackendHealth: returns 'ok', 'unhealthy', and 'disconnected' appropriately", async () => {
  // Case 1: Healthy
  let fetchMock = mockFetch(async () => {
    return new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  try {
    const h1 = await api.checkBackendHealth();
    assert.equal(h1.status, "ok");
  } finally {
    fetchMock.restore();
  }

  // Case 2: HTTP 500 error
  fetchMock = mockFetch(async () => new Response(null, { status: 500 }));
  try {
    const h2 = await api.checkBackendHealth();
    assert.equal(h2.status, "unhealthy");
  } finally {
    fetchMock.restore();
  }

  // Case 3: Network exception
  fetchMock = mockFetch(async () => {
    throw new Error("Network unreachable");
  });
  try {
    const h3 = await api.checkBackendHealth();
    assert.equal(h3.status, "disconnected");
  } finally {
    fetchMock.restore();
  }
});

test("checkOllamaConnection: reports connected status and available models", async () => {
  // Case 1: Connected with models
  let fetchMock = mockFetch(async () => {
    return new Response(
      JSON.stringify({
        models: [{ name: "deepseek-coder:6.7b" }, { name: "mistral:7b" }],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  });
  try {
    const res = await api.checkOllamaConnection();
    assert.equal(res.connected, true);
    assert.deepEqual(res.models, ["deepseek-coder:6.7b", "mistral:7b"]);
  } finally {
    fetchMock.restore();
  }

  // Case 2: Disconnected / network timeout
  fetchMock = mockFetch(async () => {
    throw new Error("Connection refused");
  });
  try {
    const res = await api.checkOllamaConnection();
    assert.equal(res.connected, false);
    assert.deepEqual(res.models, []);
  } finally {
    fetchMock.restore();
  }
});
