import type { PromoFormValues } from "./promo-types";

const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

export const SEARCH_DEBOUNCE_MS = 300;

export function createEmptyPromoForm(): PromoFormValues {
  return {
    code: "",
    campaignName: "",
    discountType: "PERCENT",
    discountValue: "10",
    applicableProducts: null,
    validFrom: "",
    validUntil: "",
    openEnded: true,
    maxTotalUses: "0",
    maxPerUser: "1",
    count: "25",
    prefix: "",
  };
}

export function createBulkPromoForm(): PromoFormValues {
  return {
    ...createEmptyPromoForm(),
    count: "100",
  };
}

export function toLocalInput(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  const offset = date.getTimezoneOffset();
  const adjusted = new Date(date.getTime() - offset * 60_000);
  return adjusted.toISOString().slice(0, 16);
}

export function fromLocalInput(value: string): string | null {
  if (!value) {
    return null;
  }
  return new Date(value).toISOString();
}

export function createRandomPromoCode(): string {
  return Array.from(
    { length: 8 },
    () => CODE_ALPHABET[Math.floor(Math.random() * CODE_ALPHABET.length)],
  ).join("");
}

export function buildCreatePromoPayload(values: PromoFormValues) {
  return {
    code: values.code.trim().toUpperCase(),
    campaign_name: values.campaignName.trim() || null,
    discount_type: values.discountType,
    discount_value: values.discountType === "FREE" ? null : Number(values.discountValue),
    applicable_products: values.applicableProducts,
    valid_from: fromLocalInput(values.validFrom),
    valid_until: values.openEnded ? null : fromLocalInput(values.validUntil),
    max_total_uses: Number(values.maxTotalUses || "0"),
    max_per_user: Number(values.maxPerUser || "1"),
  };
}

export function buildPatchPromoPayload(values: PromoFormValues) {
  return {
    campaign_name: values.campaignName.trim() || null,
    discount_type: values.discountType,
    discount_value: values.discountType === "FREE" ? null : Number(values.discountValue),
    applicable_products: values.applicableProducts,
    valid_from: fromLocalInput(values.validFrom),
    valid_until: values.openEnded ? null : fromLocalInput(values.validUntil),
    max_total_uses: Number(values.maxTotalUses || "0"),
    max_per_user: Number(values.maxPerUser || "1"),
  };
}

export function buildBulkPromoPayload(values: PromoFormValues) {
  return {
    ...buildPatchPromoPayload(values),
    count: Number(values.count || "1"),
    prefix: values.prefix.trim().toUpperCase() || null,
  };
}
