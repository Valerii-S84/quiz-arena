"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchEconomyCohorts, fetchEconomyPurchases, fetchEconomySubscriptions } from "@/lib/api";

const palette = ["#295065", "#89f5c7", "#f58d74", "#e6bc77", "#5f8ea8"];
const PRODUCT_LABELS: Record<string, string> = {
  ENERGY_10: "Energie +10",
  MEGA_PACK_15: "Mega Pack",
  STREAK_SAVER_20: "Streak Saver",
  FRIEND_CHALLENGE_5: "Duell-Ticket",
  PREMIUM_STARTER: "Premium Starter",
  PREMIUM_MONTH: "Premium Monat",
  PREMIUM_SEASON: "Premium Season",
  PREMIUM_YEAR: "Premium Jahr",
};

type RevenueByProductItem = {
  product: string;
  stars: number;
  eur: number;
};

type LtvItem = {
  cohort_week: string;
  cohort_size: number;
  revenue_stars_30d: number;
  ltv_stars_30d: number;
  ltv_eur_30d: number;
};

type PurchaseItem = {
  id: string;
  user_id: number;
  username: string | null;
  product: string;
  stars: number;
  eur: number;
  date: string | null;
  source: string;
  utm: unknown;
  status: string;
};

type PurchasesData = {
  items: PurchaseItem[];
  total: number;
  page: number;
  pages: number;
  charts: {
    revenue_by_product: RevenueByProductItem[];
    ltv_30d_by_cohort: LtvItem[];
  };
};

type SubscriptionItem = {
  id: number;
  user_id: number;
  username: string | null;
  status: string;
  starts_at: string;
  ends_at: string | null;
};

type SubscriptionsData = {
  items: SubscriptionItem[];
  total: number;
};

type CohortRow = {
  cohort_week: string;
  users: number;
  [key: string]: number | string;
};

type CohortsData = {
  week_offsets: number[];
  cohorts: CohortRow[];
};

function formatCurrency(value: number): string {
  return value.toLocaleString("de-DE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function formatProduct(code: string): string {
  return PRODUCT_LABELS[code] ?? code;
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("de-DE");
}

function formatSource(source: string): string {
  if (source === "telegram") {
    return "Telegram";
  }
  if (source === "web") {
    return "Web";
  }
  if (source === "api") {
    return "API";
  }
  return source;
}

function formatPurchaseStatus(status: string): string {
  if (status === "CREDITED") {
    return "Abgeschlossen";
  }
  if (status === "PAID_UNCREDITED") {
    return "Bezahlt (wird verbucht)";
  }
  if (status === "FAILED") {
    return "Fehlgeschlagen";
  }
  if (status === "CREATED" || status === "INVOICE_SENT") {
    return "Offen";
  }
  return status;
}

function purchaseStatusClass(status: string): string {
  if (status === "CREDITED") {
    return "border-emerald-300/70 bg-emerald-50 text-emerald-800";
  }
  if (status === "PAID_UNCREDITED") {
    return "border-amber-300/70 bg-amber-50 text-amber-800";
  }
  if (status === "FAILED") {
    return "border-red-300/70 bg-red-50 text-red-800";
  }
  return "border-ember/20 bg-white text-ember/80";
}

function daysUntil(dateValue: string | null): string {
  if (!dateValue) {
    return "Unbegrenzt";
  }
  const now = new Date();
  const endsAt = new Date(dateValue);
  const diffMs = endsAt.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays < 0) {
    return "Abgelaufen";
  }
  if (diffDays === 0) {
    return "Heute";
  }
  return `${diffDays} Tage`;
}

function readPercent(row: CohortRow, weekOffset: number): number {
  const value = row[`w${weekOffset}`];
  return typeof value === "number" ? value : 0;
}

export default function EconomyPage() {
  const purchasesQuery = useQuery<PurchasesData>({
    queryKey: ["economy", "purchases"],
    queryFn: fetchEconomyPurchases,
  });
  const subscriptionsQuery = useQuery<SubscriptionsData>({
    queryKey: ["economy", "subscriptions"],
    queryFn: fetchEconomySubscriptions,
  });
  const cohortsQuery = useQuery<CohortsData>({
    queryKey: ["economy", "cohorts"],
    queryFn: fetchEconomyCohorts,
  });

  const purchases = purchasesQuery.data;
  const subscriptions = subscriptionsQuery.data;
  const cohorts = cohortsQuery.data;
  const isLoading =
    purchasesQuery.isLoading || subscriptionsQuery.isLoading || cohortsQuery.isLoading;

  const totals = useMemo(() => {
    if (!purchases) {
      return {
        revenueStars: 0,
        revenueEur: 0,
        purchasesTotal: 0,
        avgPurchaseEur: 0,
        premiumSharePercent: 0,
      };
    }
    const revenueStars = purchases.charts.revenue_by_product.reduce(
      (sum, item) => sum + item.stars,
      0,
    );
    const revenueEur = purchases.charts.revenue_by_product.reduce((sum, item) => sum + item.eur, 0);
    const premiumStars = purchases.charts.revenue_by_product
      .filter((item) => item.product.startsWith("PREMIUM_"))
      .reduce((sum, item) => sum + item.stars, 0);
    const purchasesTotal = purchases.total;
    const avgPurchaseEur = purchasesTotal > 0 ? revenueEur / purchasesTotal : 0;
    const premiumSharePercent = revenueStars > 0 ? (premiumStars / revenueStars) * 100 : 0;
    return {
      revenueStars,
      revenueEur,
      purchasesTotal,
      avgPurchaseEur,
      premiumSharePercent,
    };
  }, [purchases]);

  const cohortRows = useMemo(() => {
    if (!cohorts) {
      return [];
    }
    return [...cohorts.cohorts].sort((a, b) => b.cohort_week.localeCompare(a.cohort_week)).slice(0, 8);
  }, [cohorts]);

  const cohortOffsets = useMemo(() => {
    if (!cohorts) {
      return [];
    }
    return [0, 1, 2, 4, 8].filter((offset) => cohorts.week_offsets.includes(offset));
  }, [cohorts]);

  const cohortAverages = useMemo(() => {
    if (!cohortRows.length) {
      return { w0: 0, w4: 0, w8: 0 };
    }
    const average = (weekOffset: number): number => {
      const sum = cohortRows.reduce((acc, row) => acc + readPercent(row, weekOffset), 0);
      return sum / cohortRows.length;
    };
    return {
      w0: average(0),
      w4: average(4),
      w8: average(8),
    };
  }, [cohortRows]);

  return (
    <main className="space-y-6 py-2 fade-in">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">Umsatz & Käufe</h1>
        <p className="mt-2 text-sm text-ember/70">
          Klare Sicht auf Einnahmen, aktive Abos und Kundenbindung ohne technische Sprache.
        </p>
      </header>

      {isLoading || !purchases ? <p className="text-sm">Daten werden geladen...</p> : null}

      {purchases ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Umsatz gesamt</p>
              <p className="mt-2 text-3xl">{formatCurrency(totals.revenueEur)}</p>
              <p className="mt-1 text-xs text-ember/70">
                {totals.revenueStars.toLocaleString("de-DE")} Sterne
              </p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Käufe gesamt</p>
              <p className="mt-2 text-3xl">{totals.purchasesTotal.toLocaleString("de-DE")}</p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Ø Kaufwert</p>
              <p className="mt-2 text-3xl">{formatCurrency(totals.avgPurchaseEur)}</p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Premium-Anteil</p>
              <p className="mt-2 text-3xl">
                {totals.premiumSharePercent.toLocaleString("de-DE", {
                  maximumFractionDigits: 1,
                })}
                %
              </p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Aktive Premium-Abos</p>
              <p className="mt-2 text-3xl">{(subscriptions?.total ?? 0).toLocaleString("de-DE")}</p>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Umsatz nach Produkt</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={purchases.charts.revenue_by_product}
                      dataKey="stars"
                      nameKey="product"
                      outerRadius={110}
                    >
                      {purchases.charts.revenue_by_product.map((_, idx) => (
                        <Cell key={idx} fill={palette[idx % palette.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-3 grid gap-2 text-sm">
                {purchases.charts.revenue_by_product.slice(0, 5).map((item, idx) => (
                  <div key={item.product} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{ backgroundColor: palette[idx % palette.length] }}
                      />
                      <span>{formatProduct(item.product)}</span>
                    </div>
                    <span className="text-ember/75">{formatCurrency(item.eur)}</span>
                  </div>
                ))}
              </div>
            </article>
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">LTV nach Kohorte (30 Tage)</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={purchases.charts.ltv_30d_by_cohort}>
                    <XAxis dataKey="cohort_week" />
                    <YAxis />
                    <Tooltip />
                    <Line dataKey="ltv_eur_30d" stroke="#295065" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-3 text-sm text-ember/75">
                Zeigt den durchschnittlichen Umsatz pro Nutzer in den ersten 30 Tagen je Startwoche.
              </p>
            </article>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Kohorten-Qualitaet</h2>
            <p className="mt-1 text-sm text-ember/70">
              Wie viele Nutzer aus einer Startwoche in Woche 0, 4 und 8 mindestens einmal kaufen.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <article className="rounded-xl border border-ember/15 bg-white/70 p-3">
                <p className="text-xs uppercase tracking-wide text-ember/60">Woche 0</p>
                <p className="mt-2 text-2xl">
                  {cohortAverages.w0.toLocaleString("de-DE", { maximumFractionDigits: 1 })}%
                </p>
              </article>
              <article className="rounded-xl border border-ember/15 bg-white/70 p-3">
                <p className="text-xs uppercase tracking-wide text-ember/60">Woche 4</p>
                <p className="mt-2 text-2xl">
                  {cohortAverages.w4.toLocaleString("de-DE", { maximumFractionDigits: 1 })}%
                </p>
              </article>
              <article className="rounded-xl border border-ember/15 bg-white/70 p-3">
                <p className="text-xs uppercase tracking-wide text-ember/60">Woche 8</p>
                <p className="mt-2 text-2xl">
                  {cohortAverages.w8.toLocaleString("de-DE", { maximumFractionDigits: 1 })}%
                </p>
              </article>
            </div>
            {cohortRows.length > 0 ? (
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-ember/20 text-left">
                      <th className="py-2">Kohorte</th>
                      <th className="py-2">Nutzer</th>
                      {cohortOffsets.map((offset) => (
                        <th key={offset} className="py-2">
                          W{offset}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {cohortRows.map((row) => (
                      <tr key={row.cohort_week} className="border-b border-ember/10">
                        <td className="py-2">{row.cohort_week}</td>
                        <td className="py-2">{row.users.toLocaleString("de-DE")}</td>
                        {cohortOffsets.map((offset) => {
                          const value = readPercent(row, offset);
                          return (
                            <td key={`${row.cohort_week}-${offset}`} className="py-2">
                              <p className="text-xs text-ember/80">
                                {value.toLocaleString("de-DE", { maximumFractionDigits: 1 })}%
                              </p>
                              <div className="mt-1 h-2 w-24 rounded-full bg-ember/10">
                                <div
                                  className="h-2 rounded-full bg-[#2f5f74]"
                                  style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
                                />
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-3 text-sm text-ember/75">Noch keine Kohorten-Daten vorhanden.</p>
            )}
          </section>

          <section className="surface overflow-x-auto rounded-2xl p-4">
            <h2 className="text-xl">Aktive Premium-Abos</h2>
            {subscriptions && subscriptions.items.length > 0 ? (
              <table className="mt-4 min-w-full text-sm">
                <thead>
                  <tr className="border-b border-ember/20 text-left">
                    <th className="py-2">Nutzer</th>
                    <th className="py-2">Start</th>
                    <th className="py-2">Ende</th>
                    <th className="py-2">Restzeit</th>
                  </tr>
                </thead>
                <tbody>
                  {subscriptions.items.slice(0, 12).map((item) => (
                    <tr key={item.id} className="border-b border-ember/10">
                      <td className="py-2">{item.username || `User ${item.user_id}`}</td>
                      <td className="py-2">{formatDateTime(item.starts_at)}</td>
                      <td className="py-2">{formatDateTime(item.ends_at)}</td>
                      <td className="py-2">{daysUntil(item.ends_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="mt-3 text-sm text-ember/75">Keine aktiven Premium-Abos gefunden.</p>
            )}
          </section>

          <section className="surface overflow-x-auto rounded-2xl p-4">
            <h2 className="text-xl">Letzte Käufe</h2>
            <table className="mt-4 min-w-full text-sm">
              <thead>
                <tr className="border-b border-ember/20 text-left">
                  <th className="py-2">Nutzer</th>
                  <th className="py-2">Produkt</th>
                  <th className="py-2">Betrag</th>
                  <th className="py-2">Datum</th>
                  <th className="py-2">Quelle</th>
                  <th className="py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {purchases.items.slice(0, 20).map((item) => (
                  <tr key={item.id} className="border-b border-ember/10">
                    <td className="py-2">{item.username || `User ${item.user_id}`}</td>
                    <td className="py-2">{formatProduct(item.product)}</td>
                    <td className="py-2">
                      {formatCurrency(item.eur)}{" "}
                      <span className="text-xs text-ember/65">
                        ({item.stars.toLocaleString("de-DE")} ⭐)
                      </span>
                    </td>
                    <td className="py-2">{item.date ? new Date(item.date).toLocaleString("de-DE") : "-"}</td>
                    <td className="py-2">{formatSource(item.source)}</td>
                    <td className="py-2">
                      <span className={`rounded-full border px-2 py-1 text-xs ${purchaseStatusClass(item.status)}`}>
                        {formatPurchaseStatus(item.status)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </main>
  );
}
