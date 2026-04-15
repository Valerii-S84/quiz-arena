export type PromoItem = {
  id: number;
  code: string;
  code_prefix: string;
  raw_code: string | null;
  can_reveal_code: boolean;
  campaign_name: string;
  discount_type: string | null;
  discount_value: number | null;
  applicable_products: string[] | null;
  valid_from: string;
  valid_until: string | null;
  max_total_uses: number;
  max_per_user: number;
  used_total: number;
  status: "active" | "inactive" | "expired";
  created_at: string;
  updated_at: string;
};

export type PromoListResponse = {
  items: PromoItem[];
  total: number;
  page: number;
  pages: number;
};

export type PromoStatsResponse = {
  used_total: number;
  reserved_active: number;
  status_totals: Record<string, number>;
  redemptions: Array<{
    user_id: number;
    redeemed_at: string;
    status: string;
    product_id: string | null;
  }>;
};

export type PromoAuditResponse = {
  items: Array<{
    id: string;
    action: string;
    admin: string;
    created_at: string;
    details: Record<string, unknown>;
  }>;
};

export type PromoProductsResponse = {
  items: Array<{
    id: string;
    title: string;
    product_type: string;
    stars_amount: number;
  }>;
};

export type PromoProduct = PromoProductsResponse["items"][number];

export type AdminSession = {
  email: string;
  role: string;
  two_factor_verified: boolean;
};

export type FlashState = {
  kind: "success" | "error";
  text: string;
};

export type PromoFormValues = {
  code: string;
  campaignName: string;
  discountType: "PERCENT" | "FIXED" | "FREE";
  discountValue: string;
  applicableProducts: string[] | null;
  validFrom: string;
  validUntil: string;
  openEnded: boolean;
  maxTotalUses: string;
  maxPerUser: string;
  count: string;
  prefix: string;
};

export type PromoCodeAvailability = {
  normalized_code: string;
  exists: boolean;
};

export type PromoCodeCsvRow = {
  code: string;
  campaign_name: string;
  discount_type: string | null;
  discount_value: number | null;
  valid_until: string | null;
};

export type CodeModalState = {
  title: string;
  campaignName: string;
  codes: string[];
  csvRows: PromoCodeCsvRow[];
};

export type BulkGenerateResponse = {
  generated: number;
  codes: string[];
  items: PromoItem[];
};

export type RevokeResponse = {
  revoked_count: number;
};

export type PromoStatusFilter = "all" | "active" | "inactive" | "expired";

export type PromoDetailTab = "params" | "stats" | "audit";

export type PromoFormMode = "create" | "edit" | "bulk";
