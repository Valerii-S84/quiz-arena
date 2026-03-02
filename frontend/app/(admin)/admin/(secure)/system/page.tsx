"use client";

import { useQuery } from "@tanstack/react-query";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchSystemHealth } from "@/lib/api";

export default function SystemPage() {
  const { data, isLoading } = useQuery({ queryKey: ["system"], queryFn: fetchSystemHealth });

  return (
    <main className="space-y-6 py-2">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">System Health</h1>
      </header>

      {isLoading || !data ? <p className="text-sm">Завантаження...</p> : null}

      {data ? (
        <>
          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Services Status</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {Object.entries(data.services).map(([key, value]: [string, any]) => (
                <article key={key} className="rounded-xl border border-ember/15 p-3 text-sm">
                  <p className="uppercase tracking-wide text-ember/60">{key}</p>
                  <p className={`mt-2 ${value.ok ? "text-emerald-700" : "text-red-700"}`}>
                    {value.ok ? "OK" : "DOWN"}
                  </p>
                </article>
              ))}
            </div>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Queue</h2>
            <p className="mt-2 text-sm">Pending: {data.queue_stats.pending}</p>
            <p className="text-sm">Failed: {data.queue_stats.failed}</p>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">API Latency (p50/p95)</h2>
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.api_latency}>
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Line dataKey="p50" stroke="#295065" strokeWidth={2} dot={false} />
                  <Line dataKey="p95" stroke="#f58d74" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">TOP-10 Errors</h2>
            <div className="mt-3 space-y-2 text-sm">
              {data.top_10_errors.map((row: any) => (
                <div key={row.type} className="rounded-lg border border-ember/15 bg-white/70 px-3 py-2">
                  {row.type}: {row.count}
                </div>
              ))}
              {data.top_10_errors.length === 0 ? <p>No errors in current window.</p> : null}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
