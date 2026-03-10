"use client";

import { useEffect, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  fetchAdminSession,
  fetchPromo,
  fetchPromoAudit,
  fetchPromoCodeAvailability,
  fetchPromoDetail,
  fetchPromoProducts,
  fetchPromoStats,
} from "@/lib/api";

type PromoItem = {
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

type PromoListResponse = {
  items: PromoItem[];
  total: number;
  page: number;
  pages: number;
};

type PromoStatsResponse = {
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

type PromoAuditResponse = {
  items: Array<{
    id: string;
    action: string;
    admin: string;
    created_at: string;
    details: Record<string, unknown>;
  }>;
};

type PromoProductsResponse = {
  items: Array<{
    id: string;
    title: string;
    product_type: string;
    stars_amount: number;
  }>;
};

type AdminSession = {
  email: string;
  role: string;
  two_factor_verified: boolean;
};

type FlashState = {
  kind: "success" | "error";
  text: string;
};

type PromoFormValues = {
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

type PromoCodeAvailability = {
  normalized_code: string;
  exists: boolean;
};

type PromoCodeCsvRow = {
  code: string;
  campaign_name: string;
  discount_type: string | null;
  discount_value: number | null;
  valid_until: string | null;
};

type CodeModalState = {
  title: string;
  campaignName: string;
  codes: string[];
  csvRows: PromoCodeCsvRow[];
};

const SEARCH_DEBOUNCE_MS = 300;
const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

function emptyForm(): PromoFormValues {
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

function formatDateTime(value: string | null): string {
  if (!value) {
    return "Ohne Enddatum";
  }
  return new Date(value).toLocaleString("de-DE");
}

function formatProducts(
  applicableProducts: string[] | null,
  products: PromoProductsResponse["items"] | undefined,
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

function formatDiscount(item: Pick<PromoItem, "discount_type" | "discount_value">): string {
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

function formatUsage(item: Pick<PromoItem, "used_total" | "max_total_uses">): string {
  if (item.max_total_uses === 0) {
    return `${item.used_total} / unbegrenzt`;
  }
  return `${item.used_total} / ${item.max_total_uses}`;
}

function statusLabel(status: PromoItem["status"]): string {
  if (status === "active") {
    return "Aktiv";
  }
  if (status === "inactive") {
    return "Inaktiv";
  }
  return "Abgelaufen";
}

function statusClass(status: PromoItem["status"]): string {
  if (status === "active") {
    return "border-emerald-300/70 bg-emerald-50 text-emerald-800";
  }
  if (status === "inactive") {
    return "border-amber-300/70 bg-amber-50 text-amber-800";
  }
  return "border-slate-300/70 bg-slate-100 text-slate-700";
}

function promoStatusTotalLabel(status: string): string {
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

function toLocalInput(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  const offset = date.getTimezoneOffset();
  const adjusted = new Date(date.getTime() - offset * 60_000);
  return adjusted.toISOString().slice(0, 16);
}

function fromLocalInput(value: string): string | null {
  if (!value) {
    return null;
  }
  return new Date(value).toISOString();
}

function randomCode(): string {
  return Array.from({ length: 8 }, () => CODE_ALPHABET[Math.floor(Math.random() * CODE_ALPHABET.length)]).join("");
}

function buildCreatePayload(values: PromoFormValues) {
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

function buildPatchPayload(values: PromoFormValues) {
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

function buildBulkPayload(values: PromoFormValues) {
  return {
    ...buildPatchPayload(values),
    count: Number(values.count || "1"),
    prefix: values.prefix.trim().toUpperCase() || null,
  };
}

async function copyText(value: string) {
  await navigator.clipboard.writeText(value);
}

function downloadCsv(rows: PromoCodeCsvRow[]) {
  const csvRows = [
    "code,campaign_name,discount_type,discount_value,valid_until",
    ...rows.map((row) =>
      [
        row.code,
        row.campaign_name,
        row.discount_type ?? "",
        row.discount_value ?? "",
        row.valid_until ?? "",
      ].join(","),
    ),
  ];
  const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "promo-codes.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function ModalFrame({
  children,
  onClose,
  wide = false,
  position = "center",
}: {
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  position?: "center" | "top";
}) {
  return (
    <div
      className={`fixed inset-0 z-40 flex justify-center bg-[#1d160f]/55 p-4 ${
        position === "top" ? "items-start pt-12 sm:pt-16" : "items-center"
      }`}
    >
      <div
        className={`surface max-h-[90vh] w-full overflow-y-auto rounded-[28px] border border-white/60 p-5 shadow-2xl ${
          wide ? "max-w-5xl" : "max-w-3xl"
        }`}
      >
        <div className="mb-4 flex items-center justify-end">
          <button onClick={onClose} className="rounded-full border border-ember/15 px-3 py-1 text-sm">
            Schließen
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function PromoFormModal({
  title,
  values,
  setValues,
  products,
  submitLabel,
  onClose,
  onSubmit,
  isPending,
  mode,
}: {
  title: string;
  values: PromoFormValues;
  setValues: Dispatch<SetStateAction<PromoFormValues>>;
  products: PromoProductsResponse["items"] | undefined;
  submitLabel: string;
  onClose: () => void;
  onSubmit: () => Promise<void>;
  isPending: boolean;
  mode: "create" | "edit" | "bulk";
}) {
  const allProductsSelected = values.applicableProducts === null;
  const normalizedCode = values.code.trim().toUpperCase();
  const codeCheckQuery = useQuery<PromoCodeAvailability>({
    queryKey: ["promo-code-check", normalizedCode],
    queryFn: () => fetchPromoCodeAvailability(normalizedCode),
    enabled: mode === "create" && normalizedCode.length >= 4,
    retry: false,
  });
  const createCodeTaken = mode === "create" && codeCheckQuery.data?.exists === true;
  const canSubmit = mode !== "create" || (normalizedCode.length >= 4 && !createCodeTaken);
  const previewMaskedCode =
    mode === "bulk"
      ? `${(values.prefix.trim().toUpperCase() || "PROMO").slice(0, 6)}XXXX`
      : `${(values.code || "PROMO").slice(0, 8).toUpperCase()}****`;

  function toggleProduct(productId: string) {
    setValues((current) => {
      const currentProducts = current.applicableProducts ?? [];
      if (currentProducts.includes(productId)) {
        const nextProducts = currentProducts.filter((item) => item !== productId);
        return { ...current, applicableProducts: nextProducts.length ? nextProducts : null };
      }
      return { ...current, applicableProducts: [...currentProducts, productId] };
    });
  }

  return (
    <ModalFrame onClose={onClose} wide position="top">
      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-5">
          <header>
            <h2 className="text-3xl">{title}</h2>
            <p className="mt-2 text-sm text-ember/70">
              Alle Promo-Texte und Operator-Felder bleiben hier direkt im Blick.
            </p>
          </header>

          {mode === "create" ? (
            <section className="rounded-2xl border border-ember/10 bg-white/70 p-4">
              <label className="block text-sm font-medium">Code</label>
              <div className="mt-2 flex gap-2">
                <input
                  value={values.code}
                  onChange={(event) => setValues((current) => ({ ...current, code: event.target.value.toUpperCase() }))}
                  placeholder="Zum Beispiel SOMMER2026"
                  className="flex-1 rounded-xl border border-ember/15 bg-white px-3 py-2"
                />
                <button
                  onClick={() =>
                    setValues((current) => ({
                      ...current,
                      code: randomCode(),
                    }))
                  }
                  className="rounded-xl border border-ember/15 px-3 py-2 text-sm"
                >
                  Generieren
                </button>
              </div>
              {normalizedCode.length > 0 ? (
                <p
                  className={`mt-3 text-xs ${
                    createCodeTaken ? "text-red-700" : "text-emerald-700"
                  }`}
                >
                  {normalizedCode.length < 4
                    ? "Der Code muss mindestens 4 Zeichen haben."
                    : codeCheckQuery.isFetching
                      ? "Code wird geprüft..."
                      : createCodeTaken
                        ? "Dieser Code ist bereits vergeben."
                        : "Der Code ist verfügbar."}
                </p>
              ) : null}
            </section>
          ) : null}

          <section className="grid gap-4 rounded-2xl border border-ember/10 bg-white/70 p-4 md:grid-cols-2">
            <label className="text-sm">
              Kampagnenname
              <input
                value={values.campaignName}
                onChange={(event) => setValues((current) => ({ ...current, campaignName: event.target.value }))}
                placeholder="Optional"
                className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
              />
            </label>
            {mode === "bulk" ? (
              <label className="text-sm">
                Präfix
                <input
                  value={values.prefix}
                  onChange={(event) => setValues((current) => ({ ...current, prefix: event.target.value.toUpperCase().slice(0, 6) }))}
                  placeholder="Optional"
                  className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
                />
              </label>
            ) : null}
            {mode === "bulk" ? (
              <label className="text-sm">
                Anzahl
                <input
                  type="number"
                  min={1}
                  max={1000}
                  value={values.count}
                  onChange={(event) => setValues((current) => ({ ...current, count: event.target.value }))}
                  className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
                />
              </label>
            ) : null}
          </section>

          <section className="rounded-2xl border border-ember/10 bg-white/70 p-4">
            <p className="text-sm font-medium">Rabattart</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {[
                { id: "PERCENT", label: "Prozent %" },
                { id: "FIXED", label: "Festbetrag" },
                { id: "FREE", label: "Kostenlos" },
              ].map((option) => (
                <button
                  key={option.id}
                  onClick={() =>
                    setValues((current) => ({
                      ...current,
                      discountType: option.id as PromoFormValues["discountType"],
                    }))
                  }
                  className={`rounded-2xl border px-4 py-3 text-left text-sm transition ${
                    values.discountType === option.id
                      ? "border-ember bg-[#f8efe1]"
                      : "border-ember/10 bg-white hover:bg-[#fbf7ef]"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div
              className={`grid transition-all ${
                values.discountType === "FREE" ? "grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] pt-4 opacity-100"
              }`}
            >
              <div className="overflow-hidden">
                <label className="text-sm">
                  Rabattwert
                  <input
                    type="number"
                    min={1}
                    value={values.discountValue}
                    onChange={(event) => setValues((current) => ({ ...current, discountValue: event.target.value }))}
                    className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
                  />
                </label>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-ember/10 bg-white/70 p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-medium">Produkte</p>
              <button
                onClick={() => setValues((current) => ({ ...current, applicableProducts: null }))}
                className={`rounded-full px-3 py-1 text-xs ${
                  allProductsSelected ? "bg-ember text-sand" : "border border-ember/15"
                }`}
              >
                Alle Produkte
              </button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {products?.map((product) => {
                const checked = values.applicableProducts?.includes(product.id) ?? false;
                return (
                  <button
                    key={product.id}
                    onClick={() => toggleProduct(product.id)}
                    className={`rounded-2xl border px-3 py-3 text-left ${
                      checked ? "border-ember bg-[#f8efe1]" : "border-ember/10 bg-white"
                    }`}
                  >
                    <p className="text-sm font-medium">{product.title}</p>
                    <p className="mt-1 text-xs text-ember/70">
                      {product.product_type} · {product.stars_amount}⭐
                    </p>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="grid gap-4 rounded-2xl border border-ember/10 bg-white/70 p-4 md:grid-cols-2">
            <label className="text-sm">
              Gültig ab
              <input
                type="datetime-local"
                value={values.validFrom}
                onChange={(event) => setValues((current) => ({ ...current, validFrom: event.target.value }))}
                className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
              />
            </label>
            <div className="text-sm">
              <label className="flex items-center gap-2 pt-7">
                <input
                  type="checkbox"
                  checked={values.openEnded}
                  onChange={(event) => setValues((current) => ({ ...current, openEnded: event.target.checked }))}
                />
                Ohne Enddatum
              </label>
              {!values.openEnded ? (
                <input
                  type="datetime-local"
                  value={values.validUntil}
                  onChange={(event) => setValues((current) => ({ ...current, validUntil: event.target.value }))}
                  className="mt-3 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
                />
              ) : null}
            </div>
          </section>

          <section className="grid gap-4 rounded-2xl border border-ember/10 bg-white/70 p-4 md:grid-cols-2">
            <label className="text-sm">
              Max. Verwendungen gesamt
              <input
                type="number"
                min={0}
                value={values.maxTotalUses}
                onChange={(event) => setValues((current) => ({ ...current, maxTotalUses: event.target.value }))}
                placeholder="0 = unbegrenzt"
                className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
              />
            </label>
            <label className="text-sm">
              Max. pro Nutzer
              <input
                type="number"
                min={1}
                value={values.maxPerUser}
                onChange={(event) => setValues((current) => ({ ...current, maxPerUser: event.target.value }))}
                className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
              />
            </label>
          </section>
        </div>

        <aside className="rounded-[28px] border border-ember/15 bg-[linear-gradient(180deg,#fff9ef,rgba(255,255,255,0.85))] p-5">
          <p className="text-xs uppercase tracking-[0.28em] text-ember/50">Vorschau</p>
          <h3 className="mt-3 text-2xl">So wirkt der Code im Alltag</h3>
          <div className="mt-5 rounded-[24px] border border-ember/10 bg-[#1f2a31] p-4 text-sand shadow-lg">
            <p className="text-sm text-sand/70">Maskierter Code</p>
            <p className="mt-2 text-2xl tracking-[0.28em]">{previewMaskedCode}</p>
            <div className="mt-4 rounded-2xl bg-sand/10 p-3 text-sm">
              <p>{values.campaignName || "Neue Kampagne"}</p>
              <p className="mt-2">
                {values.discountType === "FREE"
                  ? "Kostenlos"
                  : values.discountType === "FIXED"
                    ? `${values.discountValue || 0}⭐ Festbetrag`
                    : `${values.discountValue || 0}% Rabatt`}
              </p>
              <p className="mt-2 text-sand/70">
                {allProductsSelected ? "Alle Produkte" : `${values.applicableProducts?.length ?? 0} Produkte`}
              </p>
            </div>
          </div>

          <div className="mt-6 flex gap-2">
            <button
              onClick={() => void onSubmit()}
              disabled={isPending || !canSubmit}
              className="rounded-2xl bg-ember px-4 py-3 text-sm text-sand disabled:opacity-70"
            >
              {isPending ? "Wird gespeichert..." : submitLabel}
            </button>
            <button onClick={onClose} className="rounded-2xl border border-ember/15 px-4 py-3 text-sm">
              Abbrechen
            </button>
          </div>
        </aside>
      </div>
    </ModalFrame>
  );
}

function CodeModal({
  state,
  onClose,
  onCopyAll,
}: {
  state: CodeModalState;
  onClose: () => void;
  onCopyAll: () => Promise<void>;
}) {
  return (
    <ModalFrame onClose={onClose} wide={state.codes.length > 1}>
      <header>
        <p className="text-xs uppercase tracking-[0.26em] text-red-700">Nur einmal sichtbar</p>
        <h2 className="mt-3 text-3xl">{state.title}</h2>
        <p className="mt-2 text-sm text-ember/70">
          Nach dem Schließen kann der vollständige Code nur noch von `super_admin` erneut angezeigt werden.
        </p>
      </header>

      {state.codes.length === 1 ? (
        <div className="mt-6 rounded-[24px] border border-amber-300/60 bg-amber-50 p-5">
          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-2xl bg-white px-4 py-3 font-mono text-xl tracking-[0.24em]">
              {state.codes[0]}
            </div>
            <button onClick={onCopyAll} className="rounded-xl border border-ember/15 px-4 py-3 text-sm">
              Kopieren
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          <div className="flex flex-wrap gap-2">
            <button onClick={onCopyAll} className="rounded-xl bg-ember px-4 py-2 text-sm text-sand">
              Alle kopieren
            </button>
            <button
              onClick={() => downloadCsv(state.csvRows)}
              className="rounded-xl border border-ember/15 px-4 py-2 text-sm"
            >
              CSV herunterladen
            </button>
          </div>
          <div className="overflow-x-auto rounded-2xl border border-ember/10 bg-white/70">
            <table className="min-w-full text-sm">
              <thead className="border-b border-ember/10 bg-[#f8efe1] text-left">
                <tr>
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Kampagne</th>
                </tr>
              </thead>
              <tbody>
                {state.codes.map((code) => (
                  <tr key={code} className="border-b border-ember/10 last:border-b-0">
                    <td className="px-4 py-3 font-mono">{code}</td>
                    <td className="px-4 py-3">{state.campaignName || "Ohne Namen"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="mt-6 flex justify-end">
        <button onClick={onClose} className="rounded-2xl bg-ember px-4 py-3 text-sm text-sand">
          Ich habe den Code gesichert
        </button>
      </div>
    </ModalFrame>
  );
}

export default function PromoClientPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive" | "expired">("all");
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [flash, setFlash] = useState<FlashState | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [editPromo, setEditPromo] = useState<PromoItem | null>(null);
  const [createForm, setCreateForm] = useState<PromoFormValues>(emptyForm());
  const [bulkForm, setBulkForm] = useState<PromoFormValues>({ ...emptyForm(), count: "100" });
  const [editForm, setEditForm] = useState<PromoFormValues>(emptyForm());
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailTab, setDetailTab] = useState<"params" | "stats" | "audit">("params");
  const [revealedCode, setRevealedCode] = useState<string | null>(null);
  const [codeModal, setCodeModal] = useState<CodeModalState | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const sessionQuery = useQuery<AdminSession>({
    queryKey: ["admin-session"],
    queryFn: fetchAdminSession,
  });
  const productsQuery = useQuery<PromoProductsResponse>({
    queryKey: ["promo-products"],
    queryFn: fetchPromoProducts,
  });
  const promoQuery = useQuery<PromoListResponse>({
    queryKey: ["promo-list", statusFilter, debouncedSearch],
    queryFn: () => fetchPromo(statusFilter === "all" ? undefined : statusFilter, debouncedSearch || undefined),
  });
  const detailQuery = useQuery<PromoItem>({
    queryKey: ["promo-detail", detailId],
    queryFn: () => fetchPromoDetail(detailId as number),
    enabled: detailId !== null,
  });
  const statsQuery = useQuery<PromoStatsResponse>({
    queryKey: ["promo-stats", detailId],
    queryFn: () => fetchPromoStats(detailId as number),
    enabled: detailId !== null,
  });
  const auditQuery = useQuery<PromoAuditResponse>({
    queryKey: ["promo-audit", detailId],
    queryFn: () => fetchPromoAudit(detailId as number),
    enabled: detailId !== null,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/admin/promo", buildCreatePayload(createForm));
      return data as PromoItem;
    },
    onSuccess: async (data) => {
      setCreateOpen(false);
      setCreateForm(emptyForm());
      setCodeModal({
        title: "Code sichern",
        campaignName: data.campaign_name,
        codes: data.raw_code ? [data.raw_code] : [],
        csvRows: data.raw_code
          ? [
              {
                code: data.raw_code,
                campaign_name: data.campaign_name,
                discount_type: data.discount_type,
                discount_value: data.discount_value,
                valid_until: data.valid_until,
              },
            ]
          : [],
      });
      setFlash({ kind: "success", text: "Der Promo-Code wurde gespeichert." });
      await queryClient.invalidateQueries({ queryKey: ["promo-list"] });
    },
    onError: () => setFlash({ kind: "error", text: "Der Promo-Code konnte nicht gespeichert werden." }),
  });

  const bulkMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/admin/promo/bulk-generate", buildBulkPayload(bulkForm));
      return data as { generated: number; codes: string[]; items: PromoItem[] };
    },
    onSuccess: async (data) => {
      setBulkOpen(false);
      setCodeModal({
        title: `${data.generated} Codes wurden erzeugt`,
        campaignName: bulkForm.campaignName,
        codes: data.codes,
        csvRows: data.items.map((item, index) => ({
          code: item.raw_code ?? data.codes[index] ?? item.code,
          campaign_name: item.campaign_name,
          discount_type: item.discount_type,
          discount_value: item.discount_value,
          valid_until: item.valid_until,
        })),
      });
      setFlash({ kind: "success", text: "Die Batch-Generierung ist abgeschlossen." });
      await queryClient.invalidateQueries({ queryKey: ["promo-list"] });
    },
    onError: () => setFlash({ kind: "error", text: "Die Batch-Generierung ist fehlgeschlagen." }),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.patch(`/admin/promo/${editPromo?.id}`, buildPatchPayload(editForm));
      return data as PromoItem;
    },
    onSuccess: async () => {
      setEditPromo(null);
      setFlash({ kind: "success", text: "Die Änderungen wurden gespeichert." });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["promo-list"] }),
        queryClient.invalidateQueries({ queryKey: ["promo-detail", detailId] }),
        queryClient.invalidateQueries({ queryKey: ["promo-stats", detailId] }),
        queryClient.invalidateQueries({ queryKey: ["promo-audit", detailId] }),
      ]);
    },
    onError: () => setFlash({ kind: "error", text: "Die Änderungen konnten nicht gespeichert werden." }),
  });

  const toggleMutation = useMutation({
    mutationFn: async (promoId: number) => {
      const { data } = await api.patch(`/admin/promo/${promoId}/toggle`);
      return data as PromoItem;
    },
    onSuccess: async () => {
      setFlash({ kind: "success", text: "Der Status wurde aktualisiert." });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["promo-list"] }),
        queryClient.invalidateQueries({ queryKey: ["promo-detail", detailId] }),
      ]);
    },
    onError: () => setFlash({ kind: "error", text: "Der Status konnte nicht geändert werden." }),
  });

  const revokeMutation = useMutation({
    mutationFn: async ({ promoId, reason }: { promoId: number; reason: string | null }) => {
      const { data } = await api.post(`/admin/promo/${promoId}/revoke`, {
        reason,
      });
      return data as { revoked_count: number };
    },
    onSuccess: async (data) => {
      setFlash({
        kind: "success",
        text: data.revoked_count > 0 ? `${data.revoked_count} Reservierungen wurden widerrufen.` : "Es gab keine aktiven Reservierungen.",
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["promo-list"] }),
        queryClient.invalidateQueries({ queryKey: ["promo-stats", detailId] }),
        queryClient.invalidateQueries({ queryKey: ["promo-audit", detailId] }),
      ]);
    },
    onError: () => setFlash({ kind: "error", text: "Der Widerruf ist fehlgeschlagen." }),
  });

  const revealMutation = useMutation({
    mutationFn: async (promoId: number) => {
      const data = await fetchPromoDetail(promoId, true);
      return data as PromoItem;
    },
    onSuccess: async (data) => {
      setRevealedCode(data.raw_code);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["promo-detail", detailId] }),
        queryClient.invalidateQueries({ queryKey: ["promo-audit", detailId] }),
      ]);
    },
  });

  function openEditModal(item: PromoItem) {
    setEditPromo(item);
    setEditForm({
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
    });
  }

  async function handleCopyAll() {
    if (!codeModal || codeModal.codes.length === 0) {
      return;
    }
    await copyText(codeModal.codes.join("\n"));
    setFlash({ kind: "success", text: "Die Codes wurden in die Zwischenablage kopiert." });
  }

  async function handleRevoke(promoId: number) {
    const input = window.prompt("Optionaler Grund für den Widerruf", "");
    const reason = input === null ? null : input.trim() || null;
    await revokeMutation.mutateAsync({ promoId, reason });
  }

  return (
    <main className="space-y-6 py-2 fade-in">
      <header className="surface overflow-hidden rounded-[32px] border border-white/60 p-6">
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <p className="text-xs uppercase tracking-[0.26em] text-ember/55">Promo-Werkbank</p>
            <h1 className="mt-3 text-4xl">Codes erzeugen, prüfen und sauber nachverfolgen</h1>
            <p className="mt-3 max-w-2xl text-sm text-ember/75">
              Suche, Statuswechsel, One-time-Code-Ausgabe, Statistik und Audit liegen jetzt in einem Operator-Flow.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <button
              onClick={() => setCreateOpen(true)}
              className="rounded-[24px] bg-ember px-5 py-4 text-left text-sand shadow-lg"
            >
              <p className="text-xs uppercase tracking-[0.2em] text-sand/70">Aktion</p>
              <p className="mt-2 text-xl">Promo-Code erstellen</p>
            </button>
            <button
              onClick={() => setBulkOpen(true)}
              className="rounded-[24px] border border-ember/15 bg-white/80 px-5 py-4 text-left"
            >
              <p className="text-xs uppercase tracking-[0.2em] text-ember/55">Aktion</p>
              <p className="mt-2 text-xl">Massen-Generierung</p>
            </button>
          </div>
        </div>
      </header>

      <section className="surface rounded-[28px] p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {[
              { id: "all", label: "Alle" },
              { id: "active", label: "Aktiv" },
              { id: "inactive", label: "Inaktiv" },
              { id: "expired", label: "Abgelaufen" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id as typeof statusFilter)}
                className={`rounded-full px-4 py-2 text-sm ${
                  statusFilter === tab.id ? "bg-ember text-sand" : "border border-ember/15 bg-white"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Nach Code-Präfix oder Kampagne suchen"
            className="w-full rounded-2xl border border-ember/15 bg-white px-4 py-3 text-sm lg:max-w-md"
          />
        </div>
      </section>

      {flash ? (
        <div
          className={`rounded-2xl border px-4 py-3 text-sm ${
            flash.kind === "error" ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
          }`}
        >
          {flash.text}
        </div>
      ) : null}

      <section className="surface overflow-hidden rounded-[30px]">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="border-b border-ember/10 bg-[#f8efe1] text-left">
              <tr>
                <th className="px-4 py-4">Code</th>
                <th className="px-4 py-4">Kampagne</th>
                <th className="px-4 py-4">Rabatt</th>
                <th className="px-4 py-4">Produkte</th>
                <th className="px-4 py-4">Laufzeit</th>
                <th className="px-4 py-4">Nutzung</th>
                <th className="px-4 py-4">Status</th>
                <th className="px-4 py-4 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {promoQuery.data?.items.map((item) => (
                <tr
                  key={item.id}
                  className="cursor-pointer border-b border-ember/10 bg-white/55 transition hover:bg-[#fff8ea]"
                  onClick={() => {
                    setDetailId(item.id);
                    setDetailTab("params");
                    setRevealedCode(null);
                  }}
                >
                  <td className="px-4 py-4 font-mono tracking-[0.18em]">{item.code}</td>
                  <td className="px-4 py-4">
                    <p className="font-medium">{item.campaign_name || "Ohne Namen"}</p>
                    <p className="mt-1 text-xs text-ember/60">#{item.id}</p>
                  </td>
                  <td className="px-4 py-4">{formatDiscount(item)}</td>
                  <td className="px-4 py-4 text-xs text-ember/70">
                    {formatProducts(item.applicable_products, productsQuery.data?.items)}
                  </td>
                  <td className="px-4 py-4 text-xs text-ember/70">
                    <p>{formatDateTime(item.valid_from)}</p>
                    <p className="mt-1">bis {formatDateTime(item.valid_until)}</p>
                  </td>
                  <td className="px-4 py-4">{formatUsage(item)}</td>
                  <td className="px-4 py-4">
                    <span className={`rounded-full border px-3 py-1 text-xs ${statusClass(item.status)}`}>
                      {statusLabel(item.status)}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          openEditModal(item);
                        }}
                        className="rounded-xl border border-ember/15 px-3 py-2 text-xs"
                      >
                        Bearbeiten
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          setDetailId(item.id);
                          setDetailTab("stats");
                        }}
                        className="rounded-xl border border-ember/15 px-3 py-2 text-xs"
                      >
                        Statistik
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          void toggleMutation.mutateAsync(item.id);
                        }}
                        disabled={item.status === "expired"}
                        className="rounded-xl border border-ember/15 px-3 py-2 text-xs disabled:opacity-40"
                      >
                        {item.status === "active" ? "Deaktivieren" : "Aktivieren"}
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleRevoke(item.id);
                        }}
                        className="rounded-xl border border-ember/15 px-3 py-2 text-xs"
                      >
                        Widerrufen
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!promoQuery.isLoading && promoQuery.data?.items.length === 0 ? (
          <div className="px-4 py-8 text-sm text-ember/65">Keine Promo-Codes für diesen Filter gefunden.</div>
        ) : null}
        {promoQuery.isLoading ? <div className="px-4 py-8 text-sm">Daten werden geladen...</div> : null}
      </section>

      {createOpen ? (
        <PromoFormModal
          title="Promo-Code erstellen"
          values={createForm}
          setValues={setCreateForm}
          products={productsQuery.data?.items}
          submitLabel="Promo-Code speichern"
          onClose={() => setCreateOpen(false)}
          onSubmit={async () => {
            await createMutation.mutateAsync();
          }}
          isPending={createMutation.isPending}
          mode="create"
        />
      ) : null}

      {bulkOpen ? (
        <PromoFormModal
          title="Massen-Generierung"
          values={bulkForm}
          setValues={setBulkForm}
          products={productsQuery.data?.items}
          submitLabel="Codes erzeugen"
          onClose={() => setBulkOpen(false)}
          onSubmit={async () => {
            await bulkMutation.mutateAsync();
          }}
          isPending={bulkMutation.isPending}
          mode="bulk"
        />
      ) : null}

      {editPromo ? (
        <PromoFormModal
          title="Promo-Code bearbeiten"
          values={editForm}
          setValues={setEditForm}
          products={productsQuery.data?.items}
          submitLabel="Änderungen speichern"
          onClose={() => setEditPromo(null)}
          onSubmit={async () => {
            await updateMutation.mutateAsync();
          }}
          isPending={updateMutation.isPending}
          mode="edit"
        />
      ) : null}

      {codeModal ? (
        <CodeModal
          state={codeModal}
          onClose={() => {
            setCodeModal(null);
            void queryClient.invalidateQueries({ queryKey: ["promo-list"] });
          }}
          onCopyAll={handleCopyAll}
        />
      ) : null}

      {detailId !== null ? (
        <div className="fixed inset-y-0 right-0 z-30 w-full max-w-xl border-l border-white/60 bg-[linear-gradient(180deg,#fff8ed,rgba(244,238,228,0.98))] p-5 shadow-2xl">
          <div className="flex h-full flex-col">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.26em] text-ember/55">Details</p>
                <h2 className="mt-2 text-3xl">{detailQuery.data?.campaign_name || "Promo-Code"}</h2>
                <p className="mt-2 font-mono text-sm tracking-[0.18em]">{detailQuery.data?.code}</p>
              </div>
              <button onClick={() => setDetailId(null)} className="rounded-full border border-ember/15 px-3 py-1 text-sm">
                Schließen
              </button>
            </div>

            {sessionQuery.data?.role === "super_admin" && detailQuery.data?.can_reveal_code ? (
              <div className="mt-4 rounded-2xl border border-amber-300/60 bg-amber-50 p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => void revealMutation.mutateAsync(detailId)}
                    className="rounded-xl border border-ember/15 bg-white px-3 py-2 text-sm"
                  >
                    Vollständigen Code anzeigen
                  </button>
                  {revealedCode ? (
                    <button
                      onClick={() => void copyText(revealedCode)}
                      className="rounded-xl border border-ember/15 bg-white px-3 py-2 text-sm"
                    >
                      Kopieren
                    </button>
                  ) : null}
                </div>
                {revealedCode ? (
                  <div className="mt-3 rounded-2xl bg-white px-4 py-3 font-mono text-lg tracking-[0.24em]">
                    {revealedCode}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="mt-5 flex gap-2">
              {[
                { id: "params", label: "Parameter" },
                { id: "stats", label: "Statistik" },
                { id: "audit", label: "Audit" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setDetailTab(tab.id as typeof detailTab)}
                  className={`rounded-full px-4 py-2 text-sm ${
                    detailTab === tab.id ? "bg-ember text-sand" : "border border-ember/15 bg-white"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="mt-5 flex-1 overflow-y-auto rounded-[28px] border border-ember/10 bg-white/70 p-4">
              {detailTab === "params" ? (
                <div className="grid gap-4 text-sm sm:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Rabatt</p>
                    <p className="mt-2">{detailQuery.data ? formatDiscount(detailQuery.data) : "..."}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Produkte</p>
                    <p className="mt-2">
                      {detailQuery.data
                        ? formatProducts(detailQuery.data.applicable_products, productsQuery.data?.items)
                        : "..."}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Gültig ab</p>
                    <p className="mt-2">{detailQuery.data ? formatDateTime(detailQuery.data.valid_from) : "..."}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Gültig bis</p>
                    <p className="mt-2">{detailQuery.data ? formatDateTime(detailQuery.data.valid_until) : "..."}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Max. gesamt</p>
                    <p className="mt-2">{detailQuery.data?.max_total_uses ?? 0}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Max. pro Nutzer</p>
                    <p className="mt-2">{detailQuery.data?.max_per_user ?? 1}</p>
                  </div>
                </div>
              ) : null}

              {detailTab === "stats" ? (
                <div className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <article className="rounded-2xl border border-emerald-200/70 bg-emerald-50 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-emerald-700">Genutzt</p>
                      <p className="mt-2 text-3xl">{statsQuery.data?.used_total ?? 0}</p>
                    </article>
                    <article className="rounded-2xl border border-amber-200/70 bg-amber-50 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-amber-700">Aktive Reservierungen</p>
                      <p className="mt-2 text-3xl">{statsQuery.data?.reserved_active ?? 0}</p>
                    </article>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {["APPLIED", "RESERVED", "EXPIRED", "REVOKED"].map((status) => (
                      <article key={status} className="rounded-2xl border border-ember/10 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-ember/55">
                          {promoStatusTotalLabel(status)}
                        </p>
                        <p className="mt-2 text-2xl">{statsQuery.data?.status_totals?.[status] ?? 0}</p>
                      </article>
                    ))}
                  </div>
                  <div className="overflow-x-auto rounded-2xl border border-ember/10">
                    <table className="min-w-full text-sm">
                      <thead className="border-b border-ember/10 bg-[#f8efe1] text-left">
                        <tr>
                          <th className="px-3 py-3">Nutzer</th>
                          <th className="px-3 py-3">Zeit</th>
                          <th className="px-3 py-3">Status</th>
                          <th className="px-3 py-3">Produkt</th>
                        </tr>
                      </thead>
                      <tbody>
                        {statsQuery.data?.redemptions.map((item) => (
                          <tr key={`${item.user_id}-${item.redeemed_at}`} className="border-b border-ember/10 last:border-b-0">
                            <td className="px-3 py-3">{item.user_id}</td>
                            <td className="px-3 py-3">{formatDateTime(item.redeemed_at)}</td>
                            <td className="px-3 py-3">{item.status}</td>
                            <td className="px-3 py-3">{item.product_id ?? "Noch offen"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {detailTab === "audit" ? (
                <div className="space-y-3">
                  {auditQuery.data?.items.map((item) => (
                    <article key={item.id} className="rounded-2xl border border-ember/10 bg-white px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-medium">{item.action}</p>
                        <p className="text-xs text-ember/55">{formatDateTime(item.created_at)}</p>
                      </div>
                      <p className="mt-2 text-sm text-ember/70">{item.admin}</p>
                    </article>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              {detailQuery.data ? (
                <button onClick={() => openEditModal(detailQuery.data)} className="rounded-2xl border border-ember/15 px-4 py-3 text-sm">
                  Bearbeiten
                </button>
              ) : null}
              <button
                onClick={() => detailId !== null && void toggleMutation.mutateAsync(detailId)}
                className="rounded-2xl border border-ember/15 px-4 py-3 text-sm"
              >
                {detailQuery.data?.status === "active" ? "Deaktivieren" : "Aktivieren"}
              </button>
              <button
                onClick={() => detailId !== null && void handleRevoke(detailId)}
                className="rounded-2xl bg-ember px-4 py-3 text-sm text-sand"
              >
                Widerrufen
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
