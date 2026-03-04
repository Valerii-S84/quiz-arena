"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
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

const periods = ["7d", "30d", "90d"];
const REQUEST_STATUSES = ["NEW", "IN_PROGRESS", "DONE", "SPAM"] as const;

type OverviewData = {
  kpis: Record<string, { current: number; delta_pct: number }>;
  revenue_series: Array<Record<string, string | number>>;
  users_series: Array<Record<string, string | number>>;
  funnel: Array<Record<string, string | number>>;
  top_products: Array<Record<string, string | number>>;
  alerts: Array<{ type: string; severity: string }>;
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
  return type === "student" ? "Student" : "Partner";
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

  return (
    <main className="space-y-6 py-2">
      <header className="surface rounded-2xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-ember/60">Overview</p>
            <h1 className="mt-1 text-3xl">KPI & Funnel</h1>
          </div>
          <select
            value={period}
            onChange={(event) => setPeriod(event.target.value)}
            className="rounded-xl border border-ember/20 bg-white px-3 py-2"
          >
            {periods.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
      </header>

      {isLoading || !data ? <p className="text-sm">Lade Dashboard-Daten...</p> : null}

      {data ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {Object.entries(data.kpis).map(([key, item]) => (
              <article key={key} className="surface rounded-xl p-4">
                <p className="text-xs uppercase tracking-wide text-ember/55">{key}</p>
                <p className="mt-2 text-2xl font-semibold">{Number(item.current).toLocaleString("de-DE")}</p>
                <p className="mt-1 text-xs text-ember/70">Δ {item.delta_pct}%</p>
              </article>
            ))}
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Revenue by Day</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.revenue_series}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Line dataKey="stars" stroke="#295065" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">New vs Active Users</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.users_series}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Line dataKey="new_users" stroke="#f58d74" strokeWidth={2} dot={false} />
                    <Line dataKey="active_users" stroke="#295065" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Funnel</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.funnel} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" />
                    <YAxis type="category" dataKey="step" width={110} />
                    <Tooltip />
                    <Bar dataKey="value" fill="#89f5c7" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Top Products</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.top_products}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="product" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="revenue_stars" fill="#f58d74" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>
          </section>

          <section className="surface rounded-2xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-xl">Anfragen von Landing Page</h2>
              <p className="text-xs text-ember/60">
                {contactRequestsData ? `Gesamt: ${contactRequestsData.total}` : ""}
              </p>
            </div>

            {isContactRequestsLoading ? <p className="mt-3 text-sm">Lade Anfragen...</p> : null}

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

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Alerts</h2>
            <div className="mt-3 space-y-2">
              {data.alerts.length === 0 ? <p className="text-sm text-emerald-700">No active alerts.</p> : null}
              {data.alerts.map((alert, index) => (
                <div key={index} className="rounded-lg border border-ember/15 bg-white/70 px-3 py-2 text-sm">
                  <span className="font-medium">{alert.type}</span> • severity: {alert.severity}
                </div>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
