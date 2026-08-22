import { describe, expect, it } from "vitest";
import {
  MAX_OVERRIDE_RANGE_NIGHTS,
  nightCount,
  validateOverrideRange,
} from "./priceOverrideRange";

describe("nightCount", () => {
  it("counts a single-night range as 1", () => {
    expect(nightCount("2027-01-01", "2027-01-01")).toBe(1);
  });

  it("counts an inclusive multi-night range correctly", () => {
    expect(nightCount("2027-01-01", "2027-01-03")).toBe(3);
  });

  it("is not thrown off by a DST transition in the local timezone", () => {
    // Any local-time parsing bug would show up as an off-by-one here in a
    // timezone that observes DST — computed purely in UTC, so it can't.
    expect(nightCount("2027-03-01", "2027-03-31")).toBe(31);
  });
});

describe("validateOverrideRange", () => {
  it("accepts a valid range and values", () => {
    const result = validateOverrideRange("2027-01-01", "2027-01-10", 50_000, 40_000);
    expect(result).toEqual({ valid: true, message: "" });
  });

  it("rejects an end date before the start date", () => {
    const result = validateOverrideRange("2027-01-10", "2027-01-01", 50_000, 40_000);
    expect(result.valid).toBe(false);
  });

  it("accepts a range exactly at the night cap", () => {
    // 2027-01-01 + 179 days = 2027-06-29, an inclusive 180-night range.
    const result = validateOverrideRange("2027-01-01", "2027-06-29", 50_000, 40_000);
    expect(nightCount("2027-01-01", "2027-06-29")).toBe(MAX_OVERRIDE_RANGE_NIGHTS);
    expect(result.valid).toBe(true);
  });

  it("rejects a range one night past the cap", () => {
    const result = validateOverrideRange("2027-01-01", "2027-06-30", 50_000, 40_000);
    expect(nightCount("2027-01-01", "2027-06-30")).toBe(MAX_OVERRIDE_RANGE_NIGHTS + 1);
    expect(result.valid).toBe(false);
    expect(result.message).toContain("181");
  });

  it("rejects a full-year range (e.g. an end-date year typo)", () => {
    const result = validateOverrideRange("2027-01-01", "2027-12-31", 50_000, 40_000);
    expect(nightCount("2027-01-01", "2027-12-31")).toBe(365);
    expect(result.valid).toBe(false);
  });

  it("rejects a negative ask price", () => {
    const result = validateOverrideRange("2027-01-01", "2027-01-01", -1, 0);
    expect(result.valid).toBe(false);
  });

  it("rejects a non-integer ask price", () => {
    const result = validateOverrideRange("2027-01-01", "2027-01-01", 50_000.5, 40_000);
    expect(result.valid).toBe(false);
  });

  it("rejects a negative minimum allowed price", () => {
    const result = validateOverrideRange("2027-01-01", "2027-01-01", 50_000, -1);
    expect(result.valid).toBe(false);
  });

  it("rejects a minimum allowed price above the ask price", () => {
    const result = validateOverrideRange("2027-01-01", "2027-01-01", 40_000, 50_000);
    expect(result.valid).toBe(false);
  });

  it("accepts a minimum allowed price equal to the ask price", () => {
    const result = validateOverrideRange("2027-01-01", "2027-01-01", 50_000, 50_000);
    expect(result.valid).toBe(true);
  });
});
