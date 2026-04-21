import { screen, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQueryClient } from "@/test/render-with-query-client";

import { PromoClientShell } from "./promo-client-shell";
import type {
  AdminSession,
  BulkGenerateResponse,
  PromoAuditResponse,
  PromoItem,
  PromoListResponse,
  PromoProductsResponse,
  PromoStatsResponse,
} from "./promo-types";

const {
  mockPost,
  mockPatch,
  mockFetchAdminSession,
  mockFetchPromo,
  mockFetchPromoAudit,
  mockFetchPromoCodeAvailability,
  mockFetchPromoDetail,
  mockFetchPromoProducts,
  mockFetchPromoStats,
} = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockFetchAdminSession: vi.fn(),
  mockFetchPromo: vi.fn(),
  mockFetchPromoAudit: vi.fn(),
  mockFetchPromoCodeAvailability: vi.fn(),
  mockFetchPromoDetail: vi.fn(),
  mockFetchPromoProducts: vi.fn(),
  mockFetchPromoStats: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    post: mockPost,
    patch: mockPatch,
  },
  fetchAdminSession: () => mockFetchAdminSession(),
  fetchPromo: (status?: string, query?: string) => mockFetchPromo(status, query),
  fetchPromoAudit: (promoId: number) => mockFetchPromoAudit(promoId),
  fetchPromoCodeAvailability: (code: string) => mockFetchPromoCodeAvailability(code),
  fetchPromoDetail: (promoId: number, reveal = false) => mockFetchPromoDetail(promoId, reveal),
  fetchPromoProducts: () => mockFetchPromoProducts(),
  fetchPromoStats: (promoId: number) => mockFetchPromoStats(promoId),
}));

const adminSession: AdminSession = {
  email: "admin@example.com",
  role: "super_admin",
  two_factor_verified: true,
};

const products: PromoProductsResponse = {
  items: [
    {
      id: "worklog",
      title: "Worklog",
      product_type: "APP",
      stars_amount: 9,
    },
    {
      id: "club",
      title: "Club",
      product_type: "COURSE",
      stars_amount: 15,
    },
  ],
};

const existingPromo: PromoItem = {
  id: 17,
  code: "WELCOME****",
  code_prefix: "WELCOME",
  raw_code: null,
  can_reveal_code: true,
  campaign_name: "Willkommen",
  discount_type: "PERCENT",
  discount_value: 20,
  applicable_products: ["worklog"],
  valid_from: "2026-05-01T10:30:00.000Z",
  valid_until: "2026-05-31T22:00:00.000Z",
  max_total_uses: 50,
  max_per_user: 2,
  used_total: 5,
  status: "active",
  created_at: "2026-04-01T08:00:00.000Z",
  updated_at: "2026-04-01T08:00:00.000Z",
};

const promoList: PromoListResponse = {
  items: [existingPromo],
  total: 1,
  page: 1,
  pages: 1,
};

const promoStats: PromoStatsResponse = {
  used_total: 5,
  reserved_active: 1,
  status_totals: {
    APPLIED: 5,
    RESERVED: 1,
    EXPIRED: 0,
    REVOKED: 0,
  },
  redemptions: [],
};

const promoAudit: PromoAuditResponse = {
  items: [],
};

function renderPromoShell() {
  return renderWithQueryClient(React.createElement(PromoClientShell));
}

describe("PromoClientShell", () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockPatch.mockReset();
    mockFetchAdminSession.mockReset();
    mockFetchPromo.mockReset();
    mockFetchPromoAudit.mockReset();
    mockFetchPromoCodeAvailability.mockReset();
    mockFetchPromoDetail.mockReset();
    mockFetchPromoProducts.mockReset();
    mockFetchPromoStats.mockReset();

    mockFetchAdminSession.mockResolvedValue(adminSession);
    mockFetchPromo.mockResolvedValue(promoList);
    mockFetchPromoAudit.mockResolvedValue(promoAudit);
    mockFetchPromoCodeAvailability.mockResolvedValue({
      normalized_code: "SOMMER2026",
      exists: false,
    });
    mockFetchPromoDetail.mockResolvedValue(existingPromo);
    mockFetchPromoProducts.mockResolvedValue(products);
    mockFetchPromoStats.mockResolvedValue(promoStats);
  });

  it("creates a promo code through the create modal happy path", async () => {
    const createdPromo: PromoItem = {
      ...existingPromo,
      id: 18,
      code: "SOMMER****",
      code_prefix: "SOMMER",
      raw_code: "SOMMER2026",
      campaign_name: "Sommer Aktion",
      max_total_uses: 0,
      max_per_user: 1,
      applicable_products: ["worklog"],
      valid_from: "2026-06-01T07:30:00.000Z",
      valid_until: null,
      used_total: 0,
      status: "inactive",
    };

    mockPost.mockResolvedValueOnce({ data: createdPromo });

    const { user } = renderPromoShell();

    await screen.findByText("Willkommen");

    await user.click(screen.getByRole("button", { name: /Promo-Code erstellen$/ }));
    await user.type(screen.getByPlaceholderText("Zum Beispiel SOMMER2026"), "sommer2026");
    await user.type(screen.getByLabelText("Kampagnenname"), "Sommer Aktion");
    await user.type(screen.getByLabelText("Gültig ab"), "2026-06-01T09:30");
    await user.click(screen.getByRole("button", { name: /Worklog/ }));

    expect(await screen.findByText("Der Code ist verfügbar.")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Promo-Code speichern" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/admin/promo", {
        code: "SOMMER2026",
        campaign_name: "Sommer Aktion",
        discount_type: "PERCENT",
        discount_value: 10,
        applicable_products: ["worklog"],
        valid_from: new Date("2026-06-01T09:30").toISOString(),
        valid_until: null,
        max_total_uses: 0,
        max_per_user: 1,
      });
    });

    expect(await screen.findByText("Der Promo-Code wurde gespeichert.")).toBeTruthy();
    expect(await screen.findByText("Code sichern")).toBeTruthy();
    expect(screen.getByText("SOMMER2026")).toBeTruthy();
  });

  it("updates an existing promo code through the edit modal happy path", async () => {
    const updatedPromo: PromoItem = {
      ...existingPromo,
      campaign_name: "Willkommen Reloaded",
      applicable_products: null,
    };

    mockPatch.mockResolvedValueOnce({ data: updatedPromo });

    const { user } = renderPromoShell();

    await screen.findByText("Willkommen");

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.clear(screen.getByLabelText("Kampagnenname"));
    await user.type(screen.getByLabelText("Kampagnenname"), "Willkommen Reloaded");
    await user.click(screen.getByRole("button", { name: "Alle Produkte" }));
    await user.click(screen.getByRole("button", { name: "Änderungen speichern" }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith("/admin/promo/17", {
        campaign_name: "Willkommen Reloaded",
        discount_type: "PERCENT",
        discount_value: 20,
        applicable_products: null,
        valid_from: existingPromo.valid_from,
        valid_until: existingPromo.valid_until,
        max_total_uses: 50,
        max_per_user: 2,
      });
    });

    expect(await screen.findByText("Die Änderungen wurden gespeichert.")).toBeTruthy();
  });

  it("runs the bulk generation happy path and shows the generated codes", async () => {
    const bulkResponse: BulkGenerateResponse = {
      generated: 2,
      codes: ["BATCHA01", "BATCHA02"],
      items: [
        {
          ...existingPromo,
          id: 31,
          code: "BATCHA****",
          code_prefix: "BATCHA",
          raw_code: "BATCHA01",
          campaign_name: "Batch A",
        },
        {
          ...existingPromo,
          id: 32,
          code: "BATCHA****",
          code_prefix: "BATCHA",
          raw_code: "BATCHA02",
          campaign_name: "Batch A",
        },
      ],
    };

    mockPost.mockResolvedValueOnce({ data: bulkResponse });

    const { user } = renderPromoShell();

    await screen.findByText("Willkommen");

    await user.click(screen.getByRole("button", { name: /Massen-Generierung$/ }));
    await user.type(screen.getByLabelText("Kampagnenname"), "Batch A");
    await user.clear(screen.getByLabelText("Präfix"));
    await user.type(screen.getByLabelText("Präfix"), "batcha");
    await user.clear(screen.getByLabelText("Anzahl"));
    await user.type(screen.getByLabelText("Anzahl"), "2");
    await user.type(screen.getByLabelText("Gültig ab"), "2026-07-01T08:15");
    await user.click(screen.getByRole("button", { name: /Club/ }));
    await user.click(screen.getByRole("button", { name: "Codes erzeugen" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/admin/promo/bulk-generate", {
        campaign_name: "Batch A",
        discount_type: "PERCENT",
        discount_value: 10,
        applicable_products: ["club"],
        valid_from: new Date("2026-07-01T08:15").toISOString(),
        valid_until: null,
        max_total_uses: 0,
        max_per_user: 1,
        count: 2,
        prefix: "BATCHA",
      });
    });

    expect(await screen.findByText("Die Batch-Generierung ist abgeschlossen.")).toBeTruthy();
    expect(await screen.findByText("2 Codes wurden erzeugt")).toBeTruthy();
    expect(screen.getByText("BATCHA01")).toBeTruthy();
    expect(screen.getByText("BATCHA02")).toBeTruthy();
  });
});
