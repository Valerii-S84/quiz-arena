"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchOverview } from "@/lib/api";

const periods = ["7d", "30d", "90d"];

export default function DashboardPage() {
  const [period, setPeriod] = useState("7d");
  const { data, isLoading } = useQuery({
    queryKey: ["overview", period],
    queryFn: () => fetchOverview(period),
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

      {isLoading || !data ? <p className="text-sm">Завантаження...</p> : null}

      {data ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {Object.entries(data.kpis).map(([key, item]: [string, any]) => (
              <article key={key} className="surface rounded-xl p-4">
                <p className="text-xs uppercase tracking-wide text-ember/55">{key}</p>
                <p className="mt-2 text-2xl font-semibold">{Number(item.current).toLocaleString("uk-UA")}</p>
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
            <h2 className="text-xl">Alerts</h2>
            <div className="mt-3 space-y-2">
              {data.alerts.length === 0 ? <p className="text-sm text-emerald-700">No active alerts.</p> : null}
              {data.alerts.map((alert: any, index: number) => (
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
