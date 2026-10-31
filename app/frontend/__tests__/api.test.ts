/**
 * Unit tests for the API client utility functions.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { getToken, setToken, clearToken, exportUrl, downloadExport } from "@/lib/api";

// Provide localStorage mock for jsdom
beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Token utilities", () => {
  it("getToken returns null when no token stored", () => {
    expect(getToken()).toBeNull();
  });

  it("setToken stores the token", () => {
    setToken("my-token");
    expect(localStorage.getItem("schedulr_token")).toBe("my-token");
  });

  it("getToken returns the stored token", () => {
    localStorage.setItem("schedulr_token", "abc123");
    expect(getToken()).toBe("abc123");
  });

  it("clearToken removes the token", () => {
    localStorage.setItem("schedulr_token", "abc123");
    clearToken();
    expect(getToken()).toBeNull();
  });
});

describe("exportUrl", () => {
  it("returns a URL containing the format", () => {
    const url = exportUrl("pdf");
    expect(url).toContain("format=pdf");
    expect(url).toContain("/api/meetings/export");
  });
});

describe("downloadExport", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  it("fetches the CSV export with the Bearer header and triggers a download", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(["a,b"]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    setToken("tok");

    await downloadExport("csv");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/meetings/export?format=csv");
    expect(url).not.toContain("token=");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock");
  });

  it("rejects on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 401 })));
    await expect(downloadExport("csv")).rejects.toThrow();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
