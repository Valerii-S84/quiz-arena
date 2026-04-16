import { describe, expect, it } from "vitest";

import {
  buildBulkPromoPayload,
  buildCreatePromoPayload,
  createBulkPromoForm,
  createEmptyPromoForm,
} from "./promo-form";
import type { PromoItem } from "./promo-types";
import { createEditPromoFormValues } from "./promo-view-model";

describe("promo form state", () => {
  it("builds create payload with trimmed code and open-ended validity", () => {
    const values = {
      ...createEmptyPromoForm(),
      code: " sommer2026 ",
      campaignName: " Sommer Aktion ",
      discountType: "FREE" as const,
      applicableProducts: ["worklog"],
      validFrom: "2026-05-01T10:30",
      openEnded: true,
      maxTotalUses: "0",
      maxPerUser: "3",
    };

    expect(buildCreatePromoPayload(values)).toEqual({
      code: "SOMMER2026",
      campaign_name: "Sommer Aktion",
      discount_type: "FREE",
      discount_value: null,
      applicable_products: ["worklog"],
      valid_from: new Date("2026-05-01T10:30").toISOString(),
      valid_until: null,
      max_total_uses: 0,
      max_per_user: 3,
    });
  });

  it("builds bulk payload with normalized prefix and numeric count", () => {
    const values = {
      ...createBulkPromoForm(),
      campaignName: "Frühjahr",
      discountType: "PERCENT" as const,
      discountValue: "15",
      validFrom: "2026-04-15T08:45",
      openEnded: false,
      validUntil: "2026-04-30T23:59",
      count: "250",
      prefix: " ab12 ",
    };

    expect(buildBulkPromoPayload(values)).toEqual({
      campaign_name: "Frühjahr",
      discount_type: "PERCENT",
      discount_value: 15,
      applicable_products: null,
      valid_from: new Date("2026-04-15T08:45").toISOString(),
      valid_until: new Date("2026-04-30T23:59").toISOString(),
      max_total_uses: 0,
      max_per_user: 1,
      count: 250,
      prefix: "AB12",
    });
  });

  it("maps promo detail into edit form defaults", () => {
    const item: PromoItem = {
      id: 17,
      code: "ABCD****",
      code_prefix: "ABCD",
      raw_code: null,
      can_reveal_code: false,
      campaign_name: "Herbst",
      discount_type: "PERCENT",
      discount_value: 20,
      applicable_products: ["worklog"],
      valid_from: "2026-09-01T09:00:00.000Z",
      valid_until: null,
      max_total_uses: 50,
      max_per_user: 2,
      used_total: 0,
      status: "active",
      created_at: "2026-08-01T00:00:00.000Z",
      updated_at: "2026-08-01T00:00:00.000Z",
    };

    expect(createEditPromoFormValues(item)).toMatchObject({
      campaignName: "Herbst",
      discountType: "PERCENT",
      discountValue: "20",
      applicableProducts: ["worklog"],
      openEnded: true,
      maxTotalUses: "50",
      maxPerUser: "2",
      count: "25",
      prefix: "",
    });
  });
});
