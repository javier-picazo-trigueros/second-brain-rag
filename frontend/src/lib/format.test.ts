import { describe, expect, it } from "vitest";

import { formatDuration, formatMemory, formatNumber, median, relativeTime } from "./format";

describe("formatDuration", () => {
  it.each([
    [0, "0 ms"],
    [420, "420 ms"],
    [999.4, "999 ms"],
    [1000, "1,0 s"],
    [2349, "2,3 s"],
    [9999, "10 s"],
    [12_400, "12 s"],
    [65_000, "1 min 5 s"],
    [120_000, "2 min"],
  ])("%s ms -> %s", (ms, expected) => {
    expect(formatDuration(ms)).toBe(expected);
  });

  it("shows a dash when there is no value", () => {
    expect(formatDuration(null)).toBe("—");
  });
});

describe("formatMemory", () => {
  it.each([
    [512, "512 MiB"],
    [4915, "4,8 GiB"],
    [8188, "8,0 GiB"],
    [1024, "1,0 GiB"],
  ])("%s MiB -> %s", (mib, expected) => {
    expect(formatMemory(mib)).toBe(expected);
  });
});

describe("formatNumber", () => {
  it("uses Spanish thousands separators", () => {
    expect(formatNumber(23236)).toBe("23.236");
    expect(formatNumber(999)).toBe("999");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-11-16T12:00:00Z");
  it.each([
    ["2026-11-16T11:59:50Z", "hace unos segundos"],
    ["2026-11-16T11:55:00Z", "hace 5 min"],
    ["2026-11-16T09:00:00Z", "hace 3 h"],
    ["2026-11-15T09:00:00Z", "ayer"],
    ["2026-11-10T12:00:00Z", "hace 6 días"],
  ])("%s -> %s", (iso, expected) => {
    expect(relativeTime(iso, now)).toBe(expected);
  });

  it("says never when there is no date", () => {
    expect(relativeTime(null, now)).toBe("nunca");
  });

  it("does not show negative times for dates slightly in the future", () => {
    expect(relativeTime("2026-11-16T12:00:05Z", now)).toBe("hace unos segundos");
  });
});

describe("median", () => {
  it("returns the middle value", () => {
    expect(median([3, 1, 2])).toBe(2);
  });
  it("averages the two middle values of an even list", () => {
    expect(median([1, 2, 3, 4])).toBe(2.5);
  });
  it("is null for an empty list", () => {
    expect(median([])).toBeNull();
  });
});
