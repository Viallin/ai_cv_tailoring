import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Explicit, not relying on Testing Library's "auto cleanup" — that
// detection only fires when `afterEach` is a true test-framework global,
// which it isn't here (vite.config.ts's `test` block deliberately omits
// `globals: true` — see that file's comment for why).
afterEach(() => {
  cleanup();
});
