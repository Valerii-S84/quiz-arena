"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchContactRequests, fetchOverview, updateContactRequestStatus } from "@/lib/api";

const PERIOD_OPTIONS = [
  { value: "7d", label: "7 Tage" },
  { value: "30d", label: "30 Tage" },
  { value: "90d", label: "90 Tage" },
] as const;
const REQUEST_STATUSES = ["NEW", "IN_PROGRESS", "DONE", "SPAM"] as const;

const KPI_DEFINITIONS = [
  {
    key: "dau",
    label: "Aktive Nutzer (24h)",
    hint: "Wie viele Nutzer heute aktiv waren.",
    unit: "count",
  },
  {
    key: "wau",
    label: "Aktive Nutzer (7 Tage)",
    hint: "Wie viele Nutzer in den letzten 7 Tagen aktiv waren.",
    unit: "count",
  },
  {
    key: "mau",
    label: "Aktive Nutzer (30 Tage)",
    hint: "Wie viele Nutzer in den letzten 30 Tagen aktiv waren.",
    unit: "count",
  },
  {
    key: "new_users",
    label: "Neue Nutzer",
    hint: "Neue Registrierungen im gewählten Zeitraum.",
    unit: "count",
  },
  {
    key: "revenue_stars",
    label: "Umsatz in Sternen",
    hint: "Gesamter Umsatz in ⭐.",
    unit: "stars",
  },
  {
    key: "revenue_eur",
    label: "Umsatz in Euro",
    hint: "Geschätzter Umsatz in €.",
    unit: "eur",
  },
  {
    key: "active_subscriptions",
    label: "Aktive Premium-Abos",
    hint: "Aktive Premium-Abos jetzt.",
    unit: "count",
  },
  {
    key: "retention_d1",
    label: "Rückkehr am nächsten Tag",
    hint: "Anteil neuer Nutzer, die am Folgetag zurückkommen.",
    unit: "percent",
  },
  {
    key: "retention_d7",
    label: "Rückkehr nach 7 Tagen",
    hint: "Anteil neuer Nutzer, die nach 7 Tagen zurückkommen.",
    unit: "percent",
  },
  {
    key: "start_users",
    label: "Bot gestartet",
    hint: "Nutzer mit Start-Aktion im Zeitraum.",
    unit: "count",
  },
  {
    key: "conversion_start_to_quiz",
    label: "Von Start zu erstem Quiz",
    hint: "Wie viele nach Start auch ein Quiz beginnen.",
    unit: "percent",
  },
  {
    key: "conversion_quiz_to_purchase",
    label: "Von Quiz zu Kauf",
    hint: "Wie viele aktive Quiz-Spieler auch kaufen.",
    unit: "percent",
  },
] as const;

const FEATURE_USAGE_DEFINITIONS = [
  {
    key: "duel_created_users",
    label: "Duell erstellt",
    hint: "Nutzer, die ein Freundesduell erstellt haben.",
    unit: "count",
  },
  {
    key: "duel_completed_users",
    label: "Duell abgeschlossen",
    hint: "Nutzer mit abgeschlossenem Freundesduell.",
    unit: "count",
  },
  {
    key: "duel_completion_rate",
    label: "Duell-Abschlussrate",
    hint: "Anteil abgeschlossener Duelle im Vergleich zu erstellten Duellen.",
    unit: "percent",
  },
  {
    key: "referral_shared_users",
    label: "Einladungslink geteilt",
    hint: 'Nutzer, die "Freund einladen" geteilt haben.',
    unit: "count",
  },
  {
    key: "referral_referrers_started",
    label: "Referrer mit neuen Starts",
    hint: "Nutzer, bei denen ein neuer Freund per Code gestartet ist.",
    unit: "count",
  },
  {
    key: "daily_cup_registered_users",
    label: "Daily Cup registriert",
    hint: "Nutzer mit Registrierung im Daily Cup.",
    unit: "count",
  },
] as const;

const FUNNEL_STEP_LABELS: Record<string, string> = {
  Start: "Start",
  "First Quiz": "Erstes Quiz",
  "Streak 3+": "Streak 3+",
  Purchase: "Kauf",
};

const PRODUCT_LABELS: Record<string, string> = {
  ENERGY_10: "Energie +10",
  STREAK_SAVER_20: "Streak Saver",
  FRIEND_CHALLENGE_5: "Duell-Ticket",
  PREMIUM_STARTER: "Premium Starter",
  PREMIUM_MONTH: "Premium Monat",
  PREMIUM_SEASON: "Premium Season",
  PREMIUM_YEAR: "Premium Jahr",
};

const CHART_AXIS_TICK = {
  fill: "#7d6658",
  fontSize: 12,
};

const CHART_GRID_STROKE = "rgba(41, 80, 101, 0.12)";

const CHART_TOOLTIP_STYLE = {
  borderRadius: "18px",
  border: "1px solid rgba(41, 80, 101, 0.14)",
  boxShadow: "0 18px 44px rgba(15, 23, 42, 0.14)",
  backgroundColor: "rgba(255, 255, 255, 0.96)",
};

type KpiMetric = {
  current: number;
  previous: number;
  delta_pct: number;
};

type RevenueSeriesItem = {
  date: string;
  stars: number;
  eur: number;
};

type UsersSeriesItem = {
  date: string;
  new_users: number;
  active_users: number;
};

type HourlyActivityItem = {
  hour: number;
  active_users: number;
};

type FunnelItem = {
  step: string;
  value: number;
};

type TopProductItem = {
  product: string;
  revenue_stars: number;
};

type AlertItem = {
  type: string;
  severity: string;
  count?: number;
  from?: number;
  to?: number;
  invalid_promo_attempts_1h?: number;
};

type OverviewData = {
  period: string;
  generated_at: string;
  kpis: Record<string, KpiMetric>;
  revenue_series: RevenueSeriesItem[];
  users_series: UsersSeriesItem[];
  hourly_activity_series?: HourlyActivityItem[];
  funnel: FunnelItem[];
  top_products: TopProductItem[];
  feature_usage?: Record<string, KpiMetric>;
  alerts: AlertItem[];
};

type ContactRequestItem = {
  id: number;
  type: "student" | "partner";
  status: "NEW" | "IN_PROGRESS" | "DONE" | "SPAM";
  name: string;
  contact: string;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type ContactRequestsData = {
  items: ContactRequestItem[];
  total: number;
  page: number;
  pages: number;
};

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function formatRequestType(type: string): string {
  return type === "student" ? "Lernender" : "Partner";
}

function formatRequestStatus(status: string): string {
  if (status === "NEW") {
    return "Neu";
  }
  if (status === "IN_PROGRESS") {
    return "In Bearbeitung";
  }
  if (status === "DONE") {
    return "Erledigt";
  }
  return "Spam";
}

function buildRequestSummary(item: ContactRequestItem): string {
  if (item.type === "student") {
    const level = readString(item.payload.level) || "-";
    const format = readString(item.payload.format) || "-";
    const frequency = readString(item.payload.frequency) || "-";
    const goals = readStringArray(item.payload.goals).join(", ") || "-";
    return `Niveau: ${level} · Format: ${format} · Frequenz: ${frequency} · Ziele: ${goals}`;
  }

  const partnerType = readString(item.payload.partnerType) || "-";
  const country = readString(item.payload.country) || "-";
  const studentCount = readString(item.payload.studentCount) || "-";
  const offerings = readStringArray(item.payload.offerings).join(", ") || "-";
  return `Typ: ${partnerType} · Land: ${country} · Lernende: ${studentCount} · Angebot: ${offerings}`;
}

function getLongMessage(item: ContactRequestItem): string {
  if (item.type === "student") {
    return readString(item.payload.message);
  }
  return readString(item.payload.idea);
}

function formatValue(value: number, unit: "count" | "percent" | "eur" | "stars"): string {
  if (unit === "percent") {
    return `${value.toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;
  }
  if (unit === "eur") {
    return value.toLocaleString("de-DE", {
      style: "currency",
      currency: "EUR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
  }
  if (unit === "stars") {
    return `${value.toLocaleString("de-DE")} ⭐`;
  }
  return value.toLocaleString("de-DE");
}

function formatDelta(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("de-DE", { maximumFractionDigits: 1 })} %`;
}

function deltaClassName(value: number): string {
  if (value > 0) {
    return "text-emerald-700";
  }
  if (value < 0) {
    return "text-red-700";
  }
  return "text-ember/70";
}

function mapAlert(alert: AlertItem): { title: string; details: string; action: string } {
  if (alert.type === "webhook_errors") {
    return {
      title: "Telegram/Webhook-Fehler",
      details: `${alert.count ?? 0} Fehler in den letzten 24 Stunden erkannt.`,
      action: "Empfehlung: Worker-Logs prüfen und Telegram-Webhook-Status kontrollieren.",
    };
  }
  if (alert.type === "conversion_drop") {
    return {
      title: "Kauf-Konversion gesunken",
      details: `Von ${alert.from ?? 0}% auf ${alert.to ?? 0}% gefallen.`,
      action: "Empfehlung: Angebote, Checkout und letzte Produkt-Änderungen prüfen.",
    };
  }
  if (alert.type === "suspicious_activity") {
    return {
      title: "Auffällige Promo-Aktivität",
      details: `${alert.invalid_promo_attempts_1h ?? 0} ungültige Promo-Versuche in 1 Stunde.`,
      action: "Empfehlung: Promo-Kampagnen und Missbrauchs-Filter prüfen.",
    };
  }
  return {
    title: alert.type,
    details: "Es liegt ein Hinweis vor.",
    action: "Empfehlung: Details im System-Bereich prüfen.",
  };
}

function mapProductLabel(productCode: string): string {
  return PRODUCT_LABELS[productCode] ?? productCode;
}

function formatHourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

function formatHourRangeLabel(hour: number): string {
  const nextHour = (hour + 1) % 24;
  return `${formatHourLabel(hour)}-${formatHourLabel(nextHour)}`;
}

function formatHourlyUsers(value: number): string {
  return value.toLocaleString("de-DE", { maximumFractionDigits: 1 });
}

function formatShortDateLabel(value: string): string {
  return new Date(value).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Europe/Berlin",
  });
}

function mapFunnelStep(step: string): string {
  return FUNNEL_STEP_LABELS[step] ?? step;
}

function getMetric(metrics: Record<string, KpiMetric> | undefined, key: string): KpiMetric {
  if (!metrics) {
    return { current: 0, previous: 0, delta_pct: 0 };
  }
  return metrics[key] ?? { current: 0, previous: 0, delta_pct: 0 };
}

export default function DashboardPage() {
  const [period, setPeriod] = useState("7d");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<OverviewData>({
    queryKey: ["overview", period],
    queryFn: () => fetchOverview(period),
  });

  const { data: contactRequestsData, isLoading: isContactRequestsLoading } =
    useQuery<ContactRequestsData>({
      queryKey: ["contact-requests"],
      queryFn: fetchContactRequests,
    });

  const statusMutation = useMutation({
    mutationFn: ({ requestId, status }: { requestId: number; status: string }) =>
      updateContactRequestStatus(requestId, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["contact-requests"] });
    },
  });

  const funnelData = useMemo(() => {
    if (!data) {
      return [] as Array<{ step: string; step_label: string; value: number; conversion_from_prev: number }>;
    }
    return data.funnel.map((item, index) => {
      const previousValue = index > 0 ? Number(data.funnel[index - 1]?.value ?? 0) : 0;
      const currentValue = Number(item.value ?? 0);
      const conversion = index === 0 ? 100 : previousValue > 0 ? (currentValue / previousValue) * 100 : 0;
      return {
        step: item.step,
        step_label: mapFunnelStep(item.step),
        value: currentValue,
        conversion_from_prev: conversion,
      };
    });
  }, [data]);

  const topProductsData = useMemo(() => {
    if (!data) {
      return [] as Array<{ product: string; product_label: string; revenue_stars: number }>;
    }
    return data.top_products.map((item) => ({
      product: item.product,
      product_label: mapProductLabel(item.product),
      revenue_stars: Number(item.revenue_stars ?? 0),
    }));
  }, [data]);

  const totalRevenueStars = useMemo(() => {
    if (!data) {
      return 0;
    }
    return data.revenue_series.reduce((sum, item) => sum + Number(item.stars ?? 0), 0);
  }, [data]);

  const averageActiveUsers = useMemo(() => {
    if (!data || data.users_series.length === 0) {
      return 0;
    }
    const total = data.users_series.reduce((sum, item) => sum + Number(item.active_users ?? 0), 0);
    return total / data.users_series.length;
  }, [data]);

  const peakHourlyActivity = useMemo(() => {
    const series = data?.hourly_activity_series ?? [];
    if (series.length === 0) {
      return null;
    }
    return series.reduce((best, item) => {
      if (item.active_users > best.active_users) {
        return item;
      }
      return best;
    });
  }, [data]);

  const averageHourlyActivity = useMemo(() => {
    const series = data?.hourly_activity_series ?? [];
    if (series.length === 0) {
      return 0;
    }
    const total = series.reduce((sum, item) => sum + Number(item.active_users ?? 0), 0);
    return total / series.length;
  }, [data]);

  const topHourlyWindows = useMemo(() => {
    const series = data?.hourly_activity_series ?? [];
    return [...series]
      .filter((item) => Number(item.active_users ?? 0) > 0)
      .sort((left, right) => Number(right.active_users ?? 0) - Number(left.active_users ?? 0))
      .slice(0, 3);
  }, [data]);

  return (
    <main className="min-w-0 space-y-6 py-2">
      <header className="surface rounded-2xl p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-ember/60">Admin Übersicht</p>
            <h1 className="mt-1 text-3xl">Geschäftszahlen klar erklärt</h1>
            <p className="mt-2 text-sm text-ember/70">
              Alle Werte sind auf den gewählten Zeitraum bezogen und werden mit dem vorherigen
              gleich langen Zeitraum verglichen.
            </p>
            {data ? (
              <p className="mt-1 text-xs text-ember/60">
                Letzte Aktualisierung: {new Date(data.generated_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })} (Berlin)
              </p>
            ) : null}
          </div>
          <select
            value={period}
            onChange={(event) => setPeriod(event.target.value)}
            className="rounded-xl border border-ember/20 bg-white px-3 py-2"
          >
            {PERIOD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {isLoading || !data ? <p className="text-sm">Dashboard-Daten werden geladen...</p> : null}

      {data ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {KPI_DEFINITIONS.map((definition) => {
              const metric = getMetric(data.kpis, definition.key);
              return (
                <article key={definition.key} className="surface rounded-xl p-4">
                  <p className="text-xs uppercase tracking-wide text-ember/60">{definition.label}</p>
                  <p className="mt-2 text-2xl font-semibold">{formatValue(metric.current, definition.unit)}</p>
                  <p className={`mt-1 text-xs ${deltaClassName(metric.delta_pct)}`}>
                    Veränderung: {formatDelta(metric.delta_pct)}
                  </p>
                  <p className="mt-1 text-xs text-ember/60">
                    Vorher: {formatValue(metric.previous, definition.unit)}
                  </p>
                  <p className="mt-2 text-xs text-ember/70">{definition.hint}</p>
                </article>
              );
            })}
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Nutzung wichtiger Funktionen</h2>
            <p className="mt-1 text-sm text-ember/70">
              Diese Werte zeigen direkt, ob zentrale Features wirklich genutzt werden.
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {FEATURE_USAGE_DEFINITIONS.map((definition) => {
                const metric = getMetric(data.feature_usage, definition.key);
                return (
                  <article key={definition.key} className="rounded-xl border border-ember/15 bg-white/70 p-3">
                    <p className="text-xs uppercase tracking-wide text-ember/60">{definition.label}</p>
                    <p className="mt-1 text-xl font-semibold">{formatValue(metric.current, definition.unit)}</p>
                    <p className={`mt-1 text-xs ${deltaClassName(metric.delta_pct)}`}>
                      Veränderung: {formatDelta(metric.delta_pct)}
                    </p>
                    <p className="mt-2 text-xs text-ember/70">{definition.hint}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(18rem,0.62fr)]">
            <article className="surface overflow-hidden rounded-[32px] p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-ember/45">
                    Aktivitaet
                  </p>
                  <h2 className="mt-1 text-2xl">Bot-Aktivität nach Uhrzeit</h2>
                  <p className="mt-1 text-sm text-ember/70">
                    Zeigt, in welchen Berliner Stunden Nutzer im Bot im Schnitt aktiv sind.
                  </p>
                </div>
                <div className="rounded-full border border-ember/15 bg-white/80 px-3 py-1 text-xs text-ember/75">
                  Berlin-Zeit · Durchschnitt pro Stunde im gewählten Zeitraum
                </div>
              </div>
              <div className="mt-4 h-[24rem] rounded-[26px] border border-white/70 bg-[radial-gradient(circle_at_top_left,rgba(41,80,101,0.16),transparent_38%),radial-gradient(circle_at_top_right,rgba(137,245,199,0.16),transparent_34%),linear-gradient(180deg,rgba(255,255,255,0.94),rgba(242,247,249,0.98))] p-3">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={data.hourly_activity_series ?? []}
                    margin={{ top: 8, right: 12, left: -16, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="dashboardHourlyGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#295065" stopOpacity={0.96} />
                        <stop offset="100%" stopColor="#89f5c7" stopOpacity={0.84} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      stroke={CHART_GRID_STROKE}
                      strokeDasharray="4 8"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="hour"
                      tick={CHART_AXIS_TICK}
                      tickFormatter={formatHourLabel}
                      axisLine={false}
                      tickLine={false}
                      minTickGap={12}
                    />
                    <YAxis
                      tick={CHART_AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals
                    />
                    <Tooltip
                      cursor={{ fill: "rgba(41, 80, 101, 0.06)" }}
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelFormatter={(value) => `${formatHourLabel(Number(value))} Uhr`}
                      formatter={(value) => [
                        `${formatHourlyUsers(Number(value))} Nutzer`,
                        "Ø aktiv",
                      ]}
                    />
                    <Bar
                      dataKey="active_users"
                      name="Ø aktiv"
                      fill="url(#dashboardHourlyGradient)"
                      radius={[12, 12, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="surface rounded-[32px] p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-ember/45">
                Stunden-Insights
              </p>
              <div className="mt-4 space-y-3">
                <div className="rounded-[24px] border border-[#295065]/12 bg-[linear-gradient(135deg,rgba(41,80,101,0.12),rgba(137,245,199,0.18))] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-ember/50">Peak</p>
                  <p className="mt-2 text-2xl font-semibold text-[#1f4257]">
                    {peakHourlyActivity
                      ? formatHourRangeLabel(peakHourlyActivity.hour)
                      : "Keine Daten"}
                  </p>
                  <p className="mt-1 text-sm text-ember/70">
                    {peakHourlyActivity
                      ? `${formatHourlyUsers(peakHourlyActivity.active_users)} aktive Nutzer im Schnitt`
                      : "Im gewählten Zeitraum wurden noch keine Stundenwerte erfasst."}
                  </p>
                </div>

                <div className="rounded-[24px] border border-ember/12 bg-[#fff9f3] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-ember/50">
                    Ø pro Stunde
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-[#1f4257]">
                    {averageHourlyActivity.toLocaleString("de-DE", { maximumFractionDigits: 1 })}
                  </p>
                  <p className="mt-1 text-sm text-ember/70">
                    Durchschnittliche aktive Nutzer pro Stunde im gewählten Zeitraum.
                  </p>
                </div>

                <div className="rounded-[24px] border border-ember/12 bg-white/80 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-ember/50">
                    Top-Zeitfenster
                  </p>
                  <div className="mt-3 space-y-2">
                    {topHourlyWindows.length > 0 ? (
                      topHourlyWindows.map((item) => (
                        <div
                          key={item.hour}
                          className="flex items-center justify-between rounded-2xl border border-ember/10 bg-[#fffdf9] px-3 py-2"
                        >
                          <span className="text-sm font-medium text-[#1f4257]">
                            {formatHourRangeLabel(item.hour)}
                          </span>
                          <span className="rounded-full bg-[#1f4257] px-2.5 py-1 text-xs font-semibold text-white">
                            {formatHourlyUsers(item.active_users)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-ember/65">Noch keine Aktivitaetsdaten.</p>
                    )}
                  </div>
                </div>
              </div>
            </article>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <article className="surface overflow-hidden rounded-3xl p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl">Tagesumsatz (⭐)</h2>
                  <p className="mt-1 text-sm text-ember/70">
                    Umsatzkurve als sekundäre Geschäftssicht neben dem Aktivitätsprofil.
                  </p>
                </div>
                <div className="rounded-full border border-ember/15 bg-white/80 px-3 py-1 text-xs text-ember/75">
                  Gesamt: {totalRevenueStars.toLocaleString("de-DE")} ⭐
                </div>
              </div>
              <div className="mt-4 h-[22rem] rounded-2xl border border-white/70 bg-[radial-gradient(circle_at_top_left,rgba(137,245,199,0.22),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,248,244,0.96))] p-3">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data.revenue_series} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                    <defs>
                      <linearGradient id="dashboardRevenueGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#89f5c7" stopOpacity={0.75} />
                        <stop offset="100%" stopColor="#89f5c7" stopOpacity={0.08} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="4 8" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={CHART_AXIS_TICK}
                      tickFormatter={formatShortDateLabel}
                      axisLine={false}
                      tickLine={false}
                      minTickGap={24}
                    />
                    <YAxis tick={CHART_AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip
                      cursor={{ stroke: "#295065", strokeDasharray: "4 6", strokeOpacity: 0.35 }}
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelFormatter={(value) => formatShortDateLabel(String(value))}
                      formatter={(value) => [`${Number(value).toLocaleString("de-DE")} ⭐`, "Umsatz"]}
                    />
                    <Area
                      type="monotone"
                      dataKey="stars"
                      stroke="#295065"
                      strokeWidth={3}
                      fill="url(#dashboardRevenueGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="surface overflow-hidden rounded-3xl p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl">Neue vs. aktive Nutzer</h2>
                  <p className="mt-1 text-sm text-ember/70">
                    Besser lesbarer Vergleich zwischen Wachstum und echter Nutzung.
                  </p>
                </div>
                <div className="rounded-full border border-ember/15 bg-white/80 px-3 py-1 text-xs text-ember/75">
                  Ø aktiv: {averageActiveUsers.toLocaleString("de-DE", { maximumFractionDigits: 1 })}
                </div>
              </div>
              <div className="mt-4 h-[22rem] rounded-2xl border border-white/70 bg-[radial-gradient(circle_at_top_left,rgba(245,141,116,0.16),transparent_44%),linear-gradient(180deg,rgba(255,255,255,0.92),rgba(249,244,241,0.98))] p-3">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.users_series} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="4 8" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={CHART_AXIS_TICK}
                      tickFormatter={formatShortDateLabel}
                      axisLine={false}
                      tickLine={false}
                      minTickGap={24}
                    />
                    <YAxis tick={CHART_AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip
                      cursor={{ stroke: "#f58d74", strokeDasharray: "4 6", strokeOpacity: 0.28 }}
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelFormatter={(value) => formatShortDateLabel(String(value))}
                    />
                    <Line dataKey="new_users" name="Neu" stroke="#f58d74" strokeWidth={3} dot={false} />
                    <Line
                      dataKey="active_users"
                      name="Aktiv"
                      stroke="#295065"
                      strokeWidth={3}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </article>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <article className="surface overflow-hidden rounded-3xl p-5">
              <div>
                <h2 className="text-xl">Nutzer-Funnel</h2>
                <p className="mt-1 text-sm text-ember/70">
                  Klarere Stufenansicht statt klassischer Standardbalken.
                </p>
              </div>
              <div className="mt-4 h-[22rem] rounded-2xl border border-white/70 bg-[radial-gradient(circle_at_top_left,rgba(137,245,199,0.20),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.92),rgba(241,248,245,0.98))] p-3">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={funnelData} layout="vertical" margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                    <defs>
                      <linearGradient id="dashboardFunnelGradient" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor="#89f5c7" stopOpacity={0.98} />
                        <stop offset="100%" stopColor="#295065" stopOpacity={0.88} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="4 8" horizontal={false} />
                    <XAxis
                      type="number"
                      tick={CHART_AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="step_label"
                      width={130}
                      tick={CHART_AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                    <Bar dataKey="value" fill="url(#dashboardFunnelGradient)" radius={[0, 10, 10, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-3 space-y-1 text-xs text-ember/75">
                {funnelData.map((item, index) => (
                  <p key={`${item.step}-${index}`}>
                    {item.step_label}: {item.value.toLocaleString("de-DE")} Nutzer
                    {index > 0
                      ? ` · ${item.conversion_from_prev.toLocaleString("de-DE", {
                          maximumFractionDigits: 1,
                        })}% von der vorherigen Stufe`
                      : ""}
                  </p>
                ))}
              </div>
            </article>

            <article className="surface overflow-hidden rounded-3xl p-5">
              <div>
                <h2 className="text-xl">Top-Produkte (⭐ Umsatz)</h2>
                <p className="mt-1 text-sm text-ember/70">
                  Horizontaler Vergleich, damit Produktnamen nicht mehr gequetscht wirken.
                </p>
              </div>
              <div className="mt-4 h-[22rem] rounded-2xl border border-white/70 bg-[radial-gradient(circle_at_top_left,rgba(245,141,116,0.16),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.92),rgba(251,245,242,0.98))] p-3">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topProductsData} layout="vertical" margin={{ top: 8, right: 12, left: 8, bottom: 0 }}>
                    <defs>
                      <linearGradient id="dashboardProductsGradient" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor="#f58d74" stopOpacity={0.98} />
                        <stop offset="100%" stopColor="#e6bc77" stopOpacity={0.9} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="4 8" horizontal={false} />
                    <XAxis
                      type="number"
                      tick={CHART_AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <YAxis
                      dataKey="product_label"
                      type="category"
                      width={132}
                      tick={CHART_AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      contentStyle={CHART_TOOLTIP_STYLE}
                      formatter={(value) => [`${Number(value).toLocaleString("de-DE")} ⭐`, "Umsatz"]}
                    />
                    <Bar dataKey="revenue_stars" fill="url(#dashboardProductsGradient)" radius={[0, 10, 10, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Warnungen</h2>
            <div className="mt-3 space-y-2">
              {data.alerts.length === 0 ? (
                <p className="text-sm text-emerald-700">Aktuell keine kritischen Warnungen.</p>
              ) : null}
              {data.alerts.map((alert, index) => {
                const mapped = mapAlert(alert);
                return (
                  <article key={`${alert.type}-${index}`} className="rounded-lg border border-ember/15 bg-white/70 px-3 py-2 text-sm">
                    <p className="font-medium text-ember">{mapped.title}</p>
                    <p className="mt-1 text-ember/80">{mapped.details}</p>
                    <p className="mt-1 text-xs text-ember/65">{mapped.action}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="surface rounded-2xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-xl">Anfragen von der Landing Page</h2>
              <p className="text-xs text-ember/60">
                {contactRequestsData ? `Gesamt: ${contactRequestsData.total}` : ""}
              </p>
            </div>

            {isContactRequestsLoading ? <p className="mt-3 text-sm">Anfragen werden geladen...</p> : null}

            {!isContactRequestsLoading && (!contactRequestsData || contactRequestsData.items.length === 0) ? (
              <p className="mt-3 text-sm text-emerald-700">Noch keine Anfragen vorhanden.</p>
            ) : null}

            <div className="mt-3 space-y-3">
              {contactRequestsData?.items.map((item) => {
                const isUpdating =
                  statusMutation.isPending && statusMutation.variables?.requestId === item.id;
                const longMessage = getLongMessage(item);

                return (
                  <article key={item.id} className="rounded-xl border border-ember/15 bg-white/75 p-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-ember">{item.name}</p>
                        <p className="text-xs text-ember/70">{item.contact}</p>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="rounded-full border border-ember/20 bg-white px-2 py-1 text-xs">
                          {formatRequestType(item.type)}
                        </span>
                        <select
                          value={item.status}
                          disabled={isUpdating}
                          className="rounded-lg border border-ember/20 bg-white px-2 py-1 text-xs"
                          onChange={(event) => {
                            const nextStatus = event.target.value;
                            if (nextStatus === item.status) {
                              return;
                            }
                            statusMutation.mutate({ requestId: item.id, status: nextStatus });
                          }}
                        >
                          {REQUEST_STATUSES.map((statusOption) => (
                            <option key={statusOption} value={statusOption}>
                              {formatRequestStatus(statusOption)}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <p className="mt-2 text-xs text-ember/70">
                      {new Date(item.created_at).toLocaleString("de-DE")} · {buildRequestSummary(item)}
                    </p>

                    {longMessage ? <p className="mt-2 text-sm text-ember/85">{longMessage}</p> : null}
                  </article>
                );
              })}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
