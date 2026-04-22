import type { MetricUnit } from "./dashboard-types";

type MetricDefinition = {
  key: string;
  label: string;
  hint: string;
  unit: MetricUnit;
};

export const PERIOD_OPTIONS = [
  { value: "7d", label: "7 Tage" },
  { value: "30d", label: "30 Tage" },
  { value: "90d", label: "90 Tage" },
] as const;

export const REQUEST_STATUSES = ["NEW", "IN_PROGRESS", "DONE", "SPAM"] as const;

export const KPI_DEFINITIONS: MetricDefinition[] = [
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
];

export const FEATURE_USAGE_DEFINITIONS: MetricDefinition[] = [
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
];

export const FUNNEL_STEP_LABELS: Record<string, string> = {
  Start: "Start",
  "First Quiz": "Erstes Quiz",
  "Streak 3+": "Streak 3+",
  Purchase: "Kauf",
};

export const PRODUCT_LABELS: Record<string, string> = {
  ENERGY_10: "Energie +10",
  STREAK_SAVER_20: "Streak Saver",
  FRIEND_CHALLENGE_5: "Duell-Ticket",
  PREMIUM_STARTER: "Premium Starter",
  PREMIUM_MONTH: "Premium Monat",
  PREMIUM_SEASON: "Premium Season",
  PREMIUM_YEAR: "Premium Jahr",
};

export const CHART_AXIS_TICK = {
  fill: "#7d6658",
  fontSize: 12,
};

export const CHART_GRID_STROKE = "rgba(41, 80, 101, 0.12)";

export const CHART_TOOLTIP_STYLE = {
  borderRadius: "18px",
  border: "1px solid rgba(41, 80, 101, 0.14)",
  boxShadow: "0 18px 44px rgba(15, 23, 42, 0.14)",
  backgroundColor: "rgba(255, 255, 255, 0.96)",
};
