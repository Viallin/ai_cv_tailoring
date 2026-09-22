import { useEffect, useRef } from "react";

// Phase 20 — a minimal debounced-effect hook for the Draft screen's
// autosave (PUT .../drafts/:draftId ~1.5s after the last edit). No
// debounce library exists in this codebase yet, and nothing here needs
// one.
//
// The *initial* run never fires `callback` — the caller's first render is
// typically seeded straight from a fresh GET (see DraftScreen), so firing
// on mount would just re-PUT the exact same data it was just given.
export function useDebouncedEffect(callback: () => void, deps: unknown[], delayMs: number): void {
  const isFirstRun = useRef(true);
  // Always the latest callback, so a stale closure never fires after the
  // debounce window — deps alone (not the callback identity) decide when
  // to schedule.
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false;
      return;
    }
    const timeout = setTimeout(() => callbackRef.current(), delayMs);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `deps` is the caller-supplied dependency list, intentionally not the literal array identity
  }, deps);
}
