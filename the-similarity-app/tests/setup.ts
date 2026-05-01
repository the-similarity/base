import "@testing-library/jest-dom/vitest";

/**
 * localStorage mock for the test environment.
 *
 * Why we override: Node 25's experimental WebStorage implementation (the one
 * gated behind ``--localstorage-file``) is auto-injected into the global
 * scope BEFORE jsdom's environment runs. Because Node binds ``localStorage``
 * as a getter on ``globalThis``, the jsdom Storage instance never wins, and
 * what we end up with is a half-initialized object whose methods
 * (``getItem`` / ``setItem`` / ``removeItem`` / ``clear``) throw at runtime
 * because Node expects a file path it never received.
 *
 * Rather than chase the Node flag (which would couple our test runner to a
 * Node version) we replace ``window.localStorage`` and
 * ``globalThis.localStorage`` with a clean in-memory Map-backed Storage
 * shim for every test. Production code is unaffected — this only runs in
 * the vitest environment.
 *
 * Behavior contract:
 *   - ``setItem`` / ``getItem`` / ``removeItem`` / ``clear`` work as W3C-spec.
 *   - ``length`` and ``key(i)`` work for completeness (some libs iterate).
 *   - The store is fresh per call to {@link installLocalStorageMock}; tests
 *     should call ``localStorage.clear()`` in ``beforeEach`` if they want a
 *     clean slate (or use unique keys per test).
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

  // Re-define on both window and globalThis. Some test code reaches via
  // ``window.localStorage`` (matches production's typeof-window guard);
  // some via the global. They MUST point at the same object so a write
  // through one is visible through the other.
  Object.defineProperty(globalThis, "localStorage", {
    value: mock,
    writable: true,
    configurable: true,
  });
  if (typeof window !== "undefined") {
    Object.defineProperty(window, "localStorage", {
      value: mock,
      writable: true,
      configurable: true,
    });
  }
}

installLocalStorageMock();
