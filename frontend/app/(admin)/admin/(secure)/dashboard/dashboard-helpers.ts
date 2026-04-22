import {
  FUNNEL_STEP_LABELS,
  PRODUCT_LABELS,
} from "./dashboard-config";
import type {
  AlertItem,
  ContactRequestItem,
  HourlyActivityItem,
  KpiMetric,
  MetricUnit,
} from "./dashboard-types";

export function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

export function formatRequestType(type: string): string {
  return type === "student" ? "Lernender" : "Partner";
}

export function formatRequestStatus(status: string): string {
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

export function buildRequestSummary(item: ContactRequestItem): string {
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

export function getLongMessage(item: ContactRequestItem): string {
  if (item.type === "student") {
    return readString(item.payload.message);
  }
  return readString(item.payload.idea);
}

export function formatValue(value: number, unit: MetricUnit): string {
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

export function formatDelta(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("de-DE", { maximumFractionDigits: 1 })} %`;
}

export function deltaClassName(value: number): string {
  if (value > 0) {
    return "text-emerald-700";
  }
  if (value < 0) {
    return "text-red-700";
  }
  return "text-ember/70";
}

export function mapAlert(
  alert: AlertItem,
): { title: string; details: string; action: string } {
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

export function mapProductLabel(productCode: string): string {
  return PRODUCT_LABELS[productCode] ?? productCode;
}

export function formatHourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

export function formatHourRangeLabel(hour: number): string {
  const nextHour = (hour + 1) % 24;
  return `${formatHourLabel(hour)}-${formatHourLabel(nextHour)}`;
}

export function formatShortDateLabel(value: string): string {
  return new Date(value).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Europe/Berlin",
  });
}

export function mapFunnelStep(step: string): string {
  return FUNNEL_STEP_LABELS[step] ?? step;
}

export function getMetric(
  metrics: Record<string, KpiMetric> | undefined,
  key: string,
): KpiMetric {
  if (!metrics) {
    return { current: 0, previous: 0, delta_pct: 0 };
  }
  return metrics[key] ?? { current: 0, previous: 0, delta_pct: 0 };
}

export function findPeakHourlyActivity(
  series: HourlyActivityItem[] | undefined,
): HourlyActivityItem | null {
  if (!series || series.length === 0) {
    return null;
  }
  return series.reduce((best, item) => {
    if (item.active_users > best.active_users) {
      return item;
    }
    return best;
  });
}
