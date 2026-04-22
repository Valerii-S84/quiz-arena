export type MetricUnit = "count" | "percent" | "eur" | "stars";

export type KpiMetric = {
  current: number;
  previous: number;
  delta_pct: number;
};

export type RevenueSeriesItem = {
  date: string;
  stars: number;
  eur: number;
};

export type UsersSeriesItem = {
  date: string;
  new_users: number;
  active_users: number;
};

export type HourlyActivityItem = {
  hour: number;
  active_users: number;
};

export type FunnelItem = {
  step: string;
  value: number;
};

export type TopProductItem = {
  product: string;
  revenue_stars: number;
};

export type AlertItem = {
  type: string;
  severity: string;
  count?: number;
  from?: number;
  to?: number;
  invalid_promo_attempts_1h?: number;
};

export type OverviewData = {
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

export type ContactRequestItem = {
  id: number;
  type: "student" | "partner";
  status: "NEW" | "IN_PROGRESS" | "DONE" | "SPAM";
  name: string;
  contact: string;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ContactRequestsData = {
  items: ContactRequestItem[];
  total: number;
  page: number;
  pages: number;
};

export type FunnelChartItem = {
  step: string;
  step_label: string;
  value: number;
  conversion_from_prev: number;
};

export type TopProductChartItem = {
  product: string;
  product_label: string;
  revenue_stars: number;
};
