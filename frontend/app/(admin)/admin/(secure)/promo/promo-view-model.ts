import { toLocalInput } from "./promo-form";
import type { PromoFormValues, PromoItem, PromoProduct } from "./promo-types";

export function formatPromoDateTime(value: string | null): string {
  if (!value) {
    return "Ohne Enddatum";
  }
  return new Date(value).toLocaleString("de-DE");
}

export function formatPromoProducts(
  applicableProducts: string[] | null,
  products: PromoProduct[] | undefined,
): string {
  if (!applicableProducts || applicableProducts.length === 0) {
    return "Alle Produkte";
  }
  const titles = applicableProducts.map((productId) => {
    const product = products?.find((item) => item.id === productId);
    return product?.title ?? productId;
  });
  return titles.join(", ");
}

export function formatPromoDiscount(
  item: Pick<PromoItem, "discount_type" | "discount_value">,
): string {
  if (item.discount_type === "FREE") {
    return "Kostenlos";
  }
  if (item.discount_type === "FIXED") {
    return `${item.discount_value ?? 0}⭐ Festbetrag`;
  }
  if (item.discount_type === "PERCENT") {
    return `${item.discount_value ?? 0}% Rabatt`;
  }
  return "Premium-Gutschrift";
}

export function formatPromoUsage(
  item: Pick<PromoItem, "used_total" | "max_total_uses">,
): string {
  if (item.max_total_uses === 0) {
    return `${item.used_total} / unbegrenzt`;
  }
  return `${item.used_total} / ${item.max_total_uses}`;
}

export function promoStatusLabel(status: PromoItem["status"]): string {
  if (status === "active") {
    return "Aktiv";
  }
  if (status === "inactive") {
    return "Inaktiv";
  }
  return "Abgelaufen";
}

export function promoStatusClass(status: PromoItem["status"]): string {
  if (status === "active") {
    return "border-emerald-300/70 bg-emerald-50 text-emerald-800";
  }
  if (status === "inactive") {
    return "border-amber-300/70 bg-amber-50 text-amber-800";
  }
  return "border-slate-300/70 bg-slate-100 text-slate-700";
}

export function promoStatusTotalLabel(status: string): string {
  if (status === "APPLIED") {
    return "Eingelöst";
  }
  if (status === "RESERVED") {
    return "Reserviert";
  }
  if (status === "EXPIRED") {
    return "Abgelaufen";
  }
  if (status === "REVOKED") {
    return "Widerrufen";
  }
  return status;
}

export function createEditPromoFormValues(item: PromoItem): PromoFormValues {
  return {
    code: "",
    campaignName: item.campaign_name,
    discountType: (item.discount_type ?? "PERCENT") as PromoFormValues["discountType"],
    discountValue: item.discount_value ? String(item.discount_value) : "10",
    applicableProducts: item.applicable_products,
    validFrom: toLocalInput(item.valid_from),
    validUntil: toLocalInput(item.valid_until),
    openEnded: item.valid_until === null,
    maxTotalUses: String(item.max_total_uses),
    maxPerUser: String(item.max_per_user),
    count: "25",
    prefix: "",
  };
}
