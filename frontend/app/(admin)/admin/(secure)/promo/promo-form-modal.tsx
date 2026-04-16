import { useQuery } from "@tanstack/react-query";
import type { Dispatch, SetStateAction } from "react";

import { fetchPromoCodeAvailability } from "@/lib/api";

import { createRandomPromoCode } from "./promo-form";
import { PromoModalFrame } from "./promo-modal-frame";
import type {
  PromoCodeAvailability,
  PromoFormMode,
  PromoFormValues,
  PromoProduct,
} from "./promo-types";

type PromoFormModalProps = {
  title: string;
  values: PromoFormValues;
  setValues: Dispatch<SetStateAction<PromoFormValues>>;
  products: PromoProduct[] | undefined;
  submitLabel: string;
  onClose: () => void;
  onSubmit: () => Promise<void>;
  isPending: boolean;
  mode: PromoFormMode;
};

export function PromoFormModal({
  title,
  values,
  setValues,
  products,
  submitLabel,
  onClose,
  onSubmit,
  isPending,
  mode,
}: PromoFormModalProps) {
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
    <PromoModalFrame onClose={onClose} wide position="top">
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
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      code: event.target.value.toUpperCase(),
                    }))
                  }
                  placeholder="Zum Beispiel SOMMER2026"
                  className="flex-1 rounded-xl border border-ember/15 bg-white px-3 py-2"
                />
                <button
                  type="button"
                  onClick={() =>
                    setValues((current) => ({
                      ...current,
                      code: createRandomPromoCode(),
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
                onChange={(event) =>
                  setValues((current) => ({ ...current, campaignName: event.target.value }))
                }
                placeholder="Optional"
                className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
              />
            </label>
            {mode === "bulk" ? (
              <label className="text-sm">
                Präfix
                <input
                  value={values.prefix}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      prefix: event.target.value.toUpperCase().slice(0, 6),
                    }))
                  }
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
                  onChange={(event) =>
                    setValues((current) => ({ ...current, count: event.target.value }))
                  }
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
                  type="button"
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
                values.discountType === "FREE"
                  ? "grid-rows-[0fr] opacity-0"
                  : "grid-rows-[1fr] pt-4 opacity-100"
              }`}
            >
              <div className="overflow-hidden">
                <label className="text-sm">
                  Rabattwert
                  <input
                    type="number"
                    min={1}
                    value={values.discountValue}
                    onChange={(event) =>
                      setValues((current) => ({ ...current, discountValue: event.target.value }))
                    }
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
                type="button"
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
                    type="button"
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
                onChange={(event) =>
                  setValues((current) => ({ ...current, validFrom: event.target.value }))
                }
                className="mt-2 w-full rounded-xl border border-ember/15 bg-white px-3 py-2"
              />
            </label>
            <div className="text-sm">
              <label className="flex items-center gap-2 pt-7">
                <input
                  type="checkbox"
                  checked={values.openEnded}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      openEnded: event.target.checked,
                    }))
                  }
                />
                Ohne Enddatum
              </label>
              {!values.openEnded ? (
                <input
                  type="datetime-local"
                  value={values.validUntil}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, validUntil: event.target.value }))
                  }
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
                onChange={(event) =>
                  setValues((current) => ({ ...current, maxTotalUses: event.target.value }))
                }
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
                onChange={(event) =>
                  setValues((current) => ({ ...current, maxPerUser: event.target.value }))
                }
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
                {allProductsSelected
                  ? "Alle Produkte"
                  : `${values.applicableProducts?.length ?? 0} Produkte`}
              </p>
            </div>
          </div>

          <div className="mt-6 flex gap-2">
            <button
              type="button"
              onClick={() => void onSubmit()}
              disabled={isPending || !canSubmit}
              className="rounded-2xl bg-ember px-4 py-3 text-sm text-sand disabled:opacity-70"
            >
              {isPending ? "Wird gespeichert..." : submitLabel}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-2xl border border-ember/15 px-4 py-3 text-sm"
            >
              Abbrechen
            </button>
          </div>
        </aside>
      </div>
    </PromoModalFrame>
  );
}
