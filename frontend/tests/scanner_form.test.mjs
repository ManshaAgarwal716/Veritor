import test from "node:test";
import assert from "node:assert/strict";
import { loadTsModule, React, rtl } from "./dom_setup.mjs";

const { render, screen, fireEvent, cleanup } = rtl;

const { ScannerForm } = loadTsModule("src/components/ScannerForm.tsx");

test("ScannerForm: renders default fields, labels and ecosystem switcher", () => {
  cleanup();
  render(
    React.createElement(ScannerForm, {
      onSubmit: async () => {},
      isLoading: false,
    })
  );

  assert.ok(screen.getByText("Package Integrity Scanner"));
  assert.ok(screen.getByText("PACKAGE NAME"));
  assert.ok(screen.getByText("EXACT VERSION"));

  const pkgInput = screen.getByPlaceholderText("e.g. left-pad, @types/node");
  const verInput = screen.getByPlaceholderText("1.3.0");
  const submitBtn = screen.getByRole("button", { name: /Scan Package/i });

  assert.equal(pkgInput.value, "");
  assert.equal(verInput.value, "");
  assert.equal(submitBtn.disabled, false);
});

test("ScannerForm: switches between npm and PyPI ecosystems", () => {
  cleanup();
  render(
    React.createElement(ScannerForm, {
      onSubmit: async () => {},
      isLoading: false,
    })
  );

  const npmBtn = screen.getByRole("button", { name: "npm" });
  const pypiBtn = screen.getByRole("button", { name: "PyPI" });

  // Initial is npm
  assert.ok(screen.getByPlaceholderText("e.g. left-pad, @types/node"));

  // Switch to PyPI
  fireEvent.click(pypiBtn);
  assert.ok(screen.getByPlaceholderText("e.g. requests, urllib3"));
  assert.ok(screen.getByPlaceholderText("2.31.0"));

  // Switch back to npm
  fireEvent.click(npmBtn);
  assert.ok(screen.getByPlaceholderText("e.g. left-pad, @types/node"));
  assert.ok(screen.getByPlaceholderText("1.3.0"));
});

test("ScannerForm: validates required package name", async () => {
  cleanup();
  let submitted = false;
  render(
    React.createElement(ScannerForm, {
      onSubmit: async () => {
        submitted = true;
      },
      isLoading: false,
      initialPackage: "",
      initialVersion: "1.0.0",
    })
  );

  const form = screen.getByRole("button", { name: /Scan Package/i }).closest("form");
  fireEvent.submit(form);

  assert.equal(submitted, false, "Must not submit when package name is empty");
  assert.ok(screen.getByText("Package name is required."));
});

test("ScannerForm: validates required version and rejects latest tag", async () => {
  cleanup();
  let submitted = false;
  render(
    React.createElement(ScannerForm, {
      onSubmit: async () => {
        submitted = true;
      },
      isLoading: false,
      initialPackage: "left-pad",
      initialVersion: "",
    })
  );

  const form = screen.getByRole("button", { name: /Scan Package/i }).closest("form");
  fireEvent.submit(form);

  assert.equal(submitted, false);
  assert.ok(screen.getByText(/Exact version is required/));

  // Test "latest" tag
  const verInput = screen.getByPlaceholderText("1.3.0");
  fireEvent.change(verInput, { target: { value: "latest" } });
  fireEvent.submit(form);

  assert.equal(submitted, false);
  assert.ok(screen.getByText(/Tags like 'latest' are not supported/));
});

test("ScannerForm: validates npm package name and semver format", async () => {
  cleanup();
  let submitted = false;
  render(
    React.createElement(ScannerForm, {
      onSubmit: async () => {
        submitted = true;
      },
      isLoading: false,
      initialEcosystem: "npm",
      initialPackage: "bad name with spaces",
      initialVersion: "1.0.0",
    })
  );

  const submitBtn = screen.getByRole("button", { name: /Scan Package/i });
  fireEvent.click(submitBtn);

  assert.equal(submitted, false);
  assert.ok(screen.getByText(/Invalid npm package name format/));

  // Invalid semver
  const pkgInput = screen.getByPlaceholderText("e.g. left-pad, @types/node");
  const verInput = screen.getByPlaceholderText("1.3.0");

  fireEvent.change(pkgInput, { target: { value: "express" } });
  fireEvent.change(verInput, { target: { value: "1.0" } }); // missing patch
  fireEvent.click(submitBtn);

  assert.equal(submitted, false);
  assert.ok(screen.getByText(/Invalid npm version. Must be an exact semantic version/));
});

test("ScannerForm: validates PyPI package name and PEP 440 version", async () => {
  cleanup();
  let submitted = false;
  render(
    React.createElement(ScannerForm, {
      onSubmit: async () => {
        submitted = true;
      },
      isLoading: false,
      initialEcosystem: "pypi",
      initialPackage: "-invalid-start",
      initialVersion: "2.31.0",
    })
  );

  const submitBtn = screen.getByRole("button", { name: /Scan Package/i });
  fireEvent.click(submitBtn);

  assert.equal(submitted, false);
  assert.ok(screen.getByText(/Invalid PyPI package name format/));

  // Invalid version format
  const pkgInput = screen.getByPlaceholderText("e.g. requests, urllib3");
  const verInput = screen.getByPlaceholderText("2.31.0");

  fireEvent.change(pkgInput, { target: { value: "requests" } });
  fireEvent.change(verInput, { target: { value: "version-2" } });
  fireEvent.click(submitBtn);

  assert.equal(submitted, false);
  assert.ok(screen.getByText(/Invalid PyPI version format/));
});

test("ScannerForm: submits valid npm scan request", async () => {
  cleanup();
  let submittedPayload = null;
  render(
    React.createElement(ScannerForm, {
      onSubmit: async (req) => {
        submittedPayload = req;
      },
      isLoading: false,
      initialEcosystem: "npm",
      initialPackage: "lodash",
      initialVersion: "4.17.21",
    })
  );

  const submitBtn = screen.getByRole("button", { name: /Scan Package/i });
  fireEvent.click(submitBtn);

  assert.deepEqual(submittedPayload, {
    ecosystem: "npm",
    package_name: "lodash",
    version: "4.17.21",
  });
});

test("ScannerForm: submits valid PyPI scan request", async () => {
  cleanup();
  let submittedPayload = null;
  render(
    React.createElement(ScannerForm, {
      onSubmit: async (req) => {
        submittedPayload = req;
      },
      isLoading: false,
      initialEcosystem: "pypi",
      initialPackage: "urllib3",
      initialVersion: "2.2.1",
    })
  );

  const submitBtn = screen.getByRole("button", { name: /Scan Package/i });
  fireEvent.click(submitBtn);

  assert.deepEqual(submittedPayload, {
    ecosystem: "pypi",
    package_name: "urllib3",
    version: "2.2.1",
  });
});

test("ScannerForm: triggers onAddToWatchlist when button is clicked", () => {
  cleanup();
  let watchlistTarget = null;
  render(
    React.createElement(ScannerForm, {
      onSubmit: async () => {},
      isLoading: false,
      initialPackage: "express",
      initialVersion: "4.18.2",
      onAddToWatchlist: (eco, pkg) => {
        watchlistTarget = { eco, pkg };
      },
    })
  );

  const addBtn = screen.getByRole("button", { name: /Add to Watchlist/i });
  fireEvent.click(addBtn);

  assert.deepEqual(watchlistTarget, {
    eco: "npm",
    pkg: "express",
  });
});

test("ScannerForm: loading state disables inputs and shows analyzing spinner", () => {
  cleanup();
  render(
    React.createElement(ScannerForm, {
      onSubmit: async () => {},
      isLoading: true,
      initialPackage: "express",
      initialVersion: "4.18.2",
    })
  );

  const pkgInput = screen.getByPlaceholderText("e.g. left-pad, @types/node");
  const verInput = screen.getByPlaceholderText("1.3.0");
  const submitBtn = screen.getByRole("button", { name: /Analyzing Package/i });

  assert.equal(pkgInput.disabled, true);
  assert.equal(verInput.disabled, true);
  assert.equal(submitBtn.disabled, true);
  assert.ok(screen.getByText("Analyzing Package..."));
});
