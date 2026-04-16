import { describe, expect, it, vi } from "vitest";

import { loadPublicStats, submitAdminLogin } from "./public-home-data";

describe("public home data", () => {
  it("marks stats as available when payload is valid", async () => {
    const stats = await loadPublicStats(async () => ({
      users: 1250,
      quizzes: 8840,
    }));

    expect(stats).toEqual({
      users: 1250,
      quizzes: 8840,
      isUnavailable: false,
    });
  });

  it("marks stats as unavailable when payload is incomplete", async () => {
    const stats = await loadPublicStats(async () => ({
      users: 1250,
      quizzes: "n/a",
    }));

    expect(stats).toEqual({
      users: 1250,
      quizzes: null,
      isUnavailable: true,
    });
  });

  it("marks stats as unavailable when the request fails", async () => {
    const stats = await loadPublicStats(async () => {
      throw new Error("network");
    });

    expect(stats).toEqual({
      users: null,
      quizzes: null,
      isUnavailable: true,
    });
  });

  it("guards login submit when credentials are missing", async () => {
    const loginRequest = vi.fn();

    const result = await submitAdminLogin(
      {
        login: "   ",
        password: "",
      },
      loginRequest,
    );

    expect(loginRequest).not.toHaveBeenCalled();
    expect(result).toEqual({
      status: "error",
      feedback: "Bitte Login und Passwort eingeben.",
      redirectTo: null,
    });
  });

  it("redirects to the 2FA login flow when required", async () => {
    const result = await submitAdminLogin(
      {
        login: "admin@example.com",
        password: "secret",
      },
      async () => ({ requires_2fa: true }),
    );

    expect(result).toEqual({
      status: "idle",
      feedback: null,
      redirectTo: "/admin/login",
    });
  });

  it("returns the login error message when authentication fails", async () => {
    const result = await submitAdminLogin(
      {
        login: "admin@example.com",
        password: "secret",
      },
      async () => {
        throw new Error("auth failed");
      },
    );

    expect(result).toEqual({
      status: "error",
      feedback: "Login fehlgeschlagen. Bitte prüfe deine Daten.",
      redirectTo: null,
    });
  });
});
