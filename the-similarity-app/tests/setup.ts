import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

/**
 * Auto-cleanup of mounted React trees between tests.
 *
 * @testing-library/react auto-registers an ``afterEach(cleanup)`` hook
 * when vitest's ``globals: true`` config is set. We don't enable
 * globals (the existing tests use explicit ``import { describe, it }
 * from "vitest"`` style), so the auto-cleanup never wires up. Without
 * cleanup, every ``render()`` accumulates DOM in the shared
 * ``document.body`` and ``screen.getByLabelText`` later finds multiple
 * matches across tests. Wiring cleanup here matches what the globals
 * mode would have done.
 */
afterEach(cleanup);

/**
 * localStorage mock for the test environment.
 *
 * Why we override
 * ---------------
 * Node 25 ships an experimental ``localStorage`` global gated behind
 * ``--localstorage-file``. When the flag is absent, Node still binds
 * ``globalThis.localStorage`` to a half-initialized object whose
 * ``getItem`` / ``setItem`` / ``removeItem`` / ``clear`` methods throw
 * at runtime (the binding expects a file path it never received).
 * That breaks any test that exercises localStorage — including the
 * production code paths that read/write user preferences and
 * persistence keys on mount.
 *
 * We replace the global with a clean Map-backed Storage shim so test
 * code can call ``getItem`` / ``setItem`` / ``removeItem`` / ``clear``
 * predictably. Production code is unaffected; this only runs in the
 * vitest setup file.
 *
 * Failure mode
 * ------------
 * If the existing ``localStorage`` property is non-configurable
 * (Node's binding may be), ``Object.defineProperty`` throws. Wrapping
 * in try/catch is mandatory: a throw in setup.ts brings down the
 * vitest environment, and EVERY test in the suite then fails with
 * "document is not defined". Better to swallow + log and let the
 * partial Node binding stand than to nuke the whole runner.
 */
function installLocalStorageMock(): void {
  const store = new Map<string, string>();
  const mock: Storage = {
    get length() {
      return store.size;
    },
    clear(): void {
      store.clear();
    },
    getItem(key: string): string | null {
      return store.has(key) ? (store.get(key) as string) : null;
    },
    key(index: number): string | null {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string): void {
      store.delete(key);
    },
    setItem(key: string, value: string): void {
      store.set(String(key), String(value));
    },
  };

  // ``Object.defineProperty`` may throw if the existing binding is
  // non-configurable (Node 25 sometimes binds localStorage that way).
  // We catch and continue — the only consequence is that storage-
  // exercising tests will see Node's half-broken binding, but that's
  // strictly better than tearing down the whole environment with an
  // unhandled exception in setup.
  try {
    Object.defineProperty(globalThis, "localStorage", {
      value: mock,
      writable: true,
      configurable: true,
    });
  } catch {
    // Fall back to assignment — also works on configurable getters.
    try {
      (globalThis as { localStorage?: Storage }).localStorage = mock;
    } catch {
      // Out of options; downstream tests will work around the broken global.
    }
  }
  if (typeof window !== "undefined") {
    try {
      Object.defineProperty(window, "localStorage", {
        value: mock,
        writable: true,
        configurable: true,
      });
    } catch {
      try {
        (window as unknown as { localStorage?: Storage }).localStorage = mock;
      } catch {
        // Same — accept the loss.
      }
    }
  }
}

installLocalStorageMock();
