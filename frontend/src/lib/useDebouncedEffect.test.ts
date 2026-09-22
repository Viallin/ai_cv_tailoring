import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDebouncedEffect } from "./useDebouncedEffect";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useDebouncedEffect", () => {
  it("does not fire on the initial mount", () => {
    const callback = vi.fn();
    renderHook(() => useDebouncedEffect(callback, ["a"], 1000));

    vi.advanceTimersByTime(5000);
    expect(callback).not.toHaveBeenCalled();
  });

  it("fires delayMs after deps change", () => {
    const callback = vi.fn();
    const { rerender } = renderHook(({ dep }) => useDebouncedEffect(callback, [dep], 1000), {
      initialProps: { dep: "a" },
    });

    rerender({ dep: "b" });
    vi.advanceTimersByTime(999);
    expect(callback).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("resets the timer on every subsequent change instead of firing once per change", () => {
    const callback = vi.fn();
    const { rerender } = renderHook(({ dep }) => useDebouncedEffect(callback, [dep], 1000), {
      initialProps: { dep: "a" },
    });

    rerender({ dep: "b" });
    vi.advanceTimersByTime(600);
    rerender({ dep: "c" });
    vi.advanceTimersByTime(600);
    // 1200ms elapsed total, but never 1000ms since the *last* change.
    expect(callback).not.toHaveBeenCalled();

    vi.advanceTimersByTime(400);
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("always calls the latest callback, not a stale closure", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ dep, cb }) => useDebouncedEffect(cb, [dep], 1000),
      { initialProps: { dep: "a", cb: first } },
    );

    rerender({ dep: "b", cb: second });
    vi.advanceTimersByTime(1000);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});
