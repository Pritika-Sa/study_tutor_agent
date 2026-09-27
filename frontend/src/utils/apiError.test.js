import { describe, expect, it } from "vitest";
import { getSafeErrorMessage } from "./apiError";

describe("getSafeErrorMessage", () => {
  it("returns the backend's detail string when present", () => {
    const error = { response: { data: { detail: "Invalid email or password" } } };
    expect(getSafeErrorMessage(error)).toBe("Invalid email or password");
  });

  it("returns a connection message when there is no response at all (network error)", () => {
    const error = { message: "Network Error" };
    expect(getSafeErrorMessage(error)).toMatch(/unable to reach the server/i);
  });

  it("falls back to the provided default when detail is missing or not a string", () => {
    const error = { response: { data: {} } };
    expect(getSafeErrorMessage(error, "custom fallback")).toBe("custom fallback");
  });

  it("never surfaces raw error internals (e.g. a stack trace)", () => {
    const error = { response: { data: { detail: "Internal Server Error" } }, stack: "at Object.<anonymous>..." };
    const message = getSafeErrorMessage(error);
    expect(message).not.toContain("at Object");
  });
});
