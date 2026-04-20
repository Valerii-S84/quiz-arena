import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  TELEGRAM_BOT_START_PAYLOAD,
  TELEGRAM_BOT_URL,
  TELEGRAM_CHANNEL_URL,
  WISSEN_ARTICLES,
} from "./public-home-content";
import PublicHomeClient from "./public-home-client";

const { mockNavigateTo, mockUsePublicStats, mockRequestAdminLogin } = vi.hoisted(() => ({
  mockNavigateTo: vi.fn(),
  mockUsePublicStats: vi.fn(),
  mockRequestAdminLogin: vi.fn(),
}));

vi.mock("@/lib/browser-navigation", () => ({
  navigateTo: (path: string) => mockNavigateTo(path),
}));

vi.mock("./public-home-data", async () => {
  const actual = await vi.importActual<typeof import("./public-home-data")>("./public-home-data");

  return {
    ...actual,
    usePublicStats: () => mockUsePublicStats(),
    requestAdminLogin: (payload: { email: string; password: string }) =>
      mockRequestAdminLogin(payload),
  };
});

describe("PublicHomeClient", () => {
  beforeEach(() => {
    mockNavigateTo.mockReset();
    mockUsePublicStats.mockReturnValue({
      users: 1250,
      quizzes: 8840,
      isUnavailable: false,
    });
    mockRequestAdminLogin.mockResolvedValue({ requires_2fa: true });
  });

  it("renders public navigation entry points and opens the student wizard", async () => {
    const user = userEvent.setup();

    render(React.createElement(PublicHomeClient));

    expect(screen.getByRole("link", { name: "Kanal öffnen" }).getAttribute("href")).toBe(
      TELEGRAM_CHANNEL_URL,
    );
    expect(screen.getByRole("link", { name: "Bot öffnen" }).getAttribute("href")).toBe(
      `${TELEGRAM_BOT_URL}?start=${TELEGRAM_BOT_START_PAYLOAD}`,
    );
    expect(screen.getByText(WISSEN_ARTICLES[0].title).closest("a")?.getAttribute("href")).toBe(
      `/artikel/${WISSEN_ARTICLES[0].slug}`,
    );

    await user.click(screen.getByRole("button", { name: "Anfrage senden" }));

    expect(await screen.findByText("Schritt 1 von 3")).toBeTruthy();
  });

  it("opens the partner wizard from the public contact section", async () => {
    const user = userEvent.setup();

    render(React.createElement(PublicHomeClient));

    await user.click(screen.getByRole("button", { name: "Kontakt aufnehmen" }));

    expect(await screen.findByText("Schritt 1 von 2")).toBeTruthy();
  });

  it("submits the public admin entry modal and redirects into the login flow", async () => {
    const user = userEvent.setup();

    render(React.createElement(PublicHomeClient));

    await user.click(screen.getByRole("button", { name: "Admin Login öffnen" }));
    await user.type(screen.getByPlaceholderText("Login"), "admin@example.com");
    await user.type(screen.getByPlaceholderText("Passwort"), "secret123");
    await user.click(screen.getByRole("button", { name: "Einloggen" }));

    await waitFor(() => {
      expect(mockRequestAdminLogin).toHaveBeenCalledWith({
        email: "admin@example.com",
        password: "secret123",
      });
      expect(mockNavigateTo).toHaveBeenCalledWith("/admin/login");
    });
  });
});
