import { afterEach, describe, expect, it } from "vitest";

import {
  getBrowserApiBaseUrl,
  getBrowserApiUrl,
  getServerApiBaseUrl,
  getServerApiUrl,
} from "./api-config";

const ORIGINAL_NODE_ENV = process.env.NODE_ENV;
const ORIGINAL_NEXT_PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL;
const ORIGINAL_API_INTERNAL_URL = process.env.API_INTERNAL_URL;

function setNodeEnv(value: string | undefined) {
  (process.env as Record<string, string | undefined>).NODE_ENV = value;
}

function restoreEnv(name: "NEXT_PUBLIC_API_URL" | "API_INTERNAL_URL", value: string | undefined) {
  if (value === undefined) {
    delete process.env[name];
    return;
  }

  process.env[name] = value;
}

afterEach(() => {
  setNodeEnv(ORIGINAL_NODE_ENV);
  restoreEnv("NEXT_PUBLIC_API_URL", ORIGINAL_NEXT_PUBLIC_API_URL);
  restoreEnv("API_INTERNAL_URL", ORIGINAL_API_INTERNAL_URL);
});

describe("api config", () => {
  it("uses the same-origin /api prefix by default outside development", () => {
    setNodeEnv("production");
    delete process.env.NEXT_PUBLIC_API_URL;
    delete process.env.API_INTERNAL_URL;

    expect(getBrowserApiBaseUrl()).toBe("/api");
    expect(getBrowserApiUrl("/admin/auth/logout")).toBe("/api/admin/auth/logout");
  });

  it("keeps the direct localhost backend default for local development", () => {
    setNodeEnv("development");
    delete process.env.NEXT_PUBLIC_API_URL;
    delete process.env.API_INTERNAL_URL;

    expect(getBrowserApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("normalizes and uses the configured public browser API URL when present", () => {
    setNodeEnv("production");
    process.env.NEXT_PUBLIC_API_URL = " https://example.com/api/ ";
    delete process.env.API_INTERNAL_URL;

    expect(getBrowserApiBaseUrl()).toBe("https://example.com/api");
    expect(getBrowserApiUrl("/contact")).toBe("https://example.com/api/contact");
  });

  it("prefers API_INTERNAL_URL for server-side requests", () => {
    setNodeEnv("production");
    process.env.NEXT_PUBLIC_API_URL = "/api";
    process.env.API_INTERNAL_URL = "http://backend:8000/";

    expect(getServerApiBaseUrl()).toBe("http://backend:8000");
    expect(getServerApiUrl("/admin/auth/session")).toBe("http://backend:8000/admin/auth/session");
  });

  it("ignores a relative public API URL for server requests when no internal URL is set", () => {
    setNodeEnv("production");
    process.env.NEXT_PUBLIC_API_URL = "/api";
    delete process.env.API_INTERNAL_URL;

    expect(getServerApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("falls back to an absolute NEXT_PUBLIC_API_URL for server requests when no internal URL is set", () => {
    setNodeEnv("production");
    process.env.NEXT_PUBLIC_API_URL = "https://deutchquizarena.de/api/";
    delete process.env.API_INTERNAL_URL;

    expect(getServerApiBaseUrl()).toBe("https://deutchquizarena.de/api");
  });
});
