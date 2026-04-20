import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";

import AdminLoginPage from "./page";

const { mockNavigateTo, mockPost } = vi.hoisted(() => ({
  mockNavigateTo: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("@/lib/browser-navigation", () => ({
  navigateTo: (path: string) => mockNavigateTo(path),
}));

vi.mock("@/lib/api", () => ({
  api: {
    post: mockPost,
  },
}));

describe("AdminLoginPage", () => {
  beforeEach(() => {
    mockNavigateTo.mockReset();
    mockPost.mockReset();
  });

  it("redirects directly to the dashboard when 2FA is not required", async () => {
    const user = userEvent.setup();

    mockPost.mockResolvedValueOnce({
      data: {
        requires_2fa: false,
      },
    });

    render(React.createElement(AdminLoginPage));

    await user.type(screen.getByPlaceholderText("Email"), "admin@example.com");
    await user.type(screen.getByPlaceholderText("Password"), "secret123");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/admin/auth/login", {
        email: "admin@example.com",
        password: "secret123",
      });
      expect(mockNavigateTo).toHaveBeenCalledWith("/admin/dashboard");
    });
  });

  it("continues with 2FA verification before redirecting to the dashboard", async () => {
    const user = userEvent.setup();

    mockPost.mockImplementation((url: string) => {
      if (url === "/admin/auth/login") {
        return Promise.resolve({
          data: {
            requires_2fa: true,
          },
        });
      }

      if (url === "/admin/auth/2fa/verify") {
        return Promise.resolve({ data: {} });
      }

      return Promise.reject(new Error(`Unexpected API call: ${url}`));
    });

    render(React.createElement(AdminLoginPage));

    await user.type(screen.getByPlaceholderText("Email"), "admin@example.com");
    await user.type(screen.getByPlaceholderText("Password"), "secret123");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    await screen.findByPlaceholderText("2FA Code");

    await user.type(screen.getByPlaceholderText("2FA Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify 2FA" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenNthCalledWith(2, "/admin/auth/2fa/verify", {
        code: "123456",
      });
      expect(mockNavigateTo).toHaveBeenCalledWith("/admin/dashboard");
    });
  });
});
