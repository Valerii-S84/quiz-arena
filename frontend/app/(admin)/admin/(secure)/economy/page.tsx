"use client";

import { useQuery } from "@tanstack/react-query";
import { Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchEconomyPurchases } from "@/lib/api";

const palette = ["#295065", "#89f5c7", "#f58d74", "#e6bc77", "#5f8ea8"];

export default function EconomyPage() {
  const { data, isLoading } = useQuery({ queryKey: ["economy", "purchases"], queryFn: fetchEconomyPurchases });

  return (
    <main className="space-y-6 py-2">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">Umsatz & Käufe</h1>
        <p className="mt-2 text-sm text-ember/70">Käufe, Abos, Kohorten und LTV.</p>
      </header>

      {isLoading || !data ? <p className="text-sm">Daten werden geladen...</p> : null}

      {data ? (
        <>
          <section className="grid gap-4 lg:grid-cols-2">
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Umsatz nach Produkt</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={data.charts.revenue_by_product} dataKey="stars" nameKey="product" outerRadius={110}>
                      {data.charts.revenue_by_product.map((_: any, idx: number) => (
                        <Cell key={idx} fill={palette[idx % palette.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </article>
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">LTV-Kurve</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.charts.ltv_30d_by_cohort}>
                    <XAxis dataKey="cohort_week" />
                    <YAxis />
                    <Tooltip />
                    <Line dataKey="ltv_stars_30d" stroke="#295065" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </article>
          </section>

          <section className="surface overflow-x-auto rounded-2xl p-4">
            <h2 className="text-xl">Käufe</h2>
            <table className="mt-4 min-w-full text-sm">
              <thead>
                <tr className="border-b border-ember/20 text-left">
                  <th className="py-2">Nutzer</th>
                  <th className="py-2">Produkt</th>
                  <th className="py-2">Stars</th>
                  <th className="py-2">EUR</th>
                  <th className="py-2">Datum</th>
                  <th className="py-2">Quelle</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item: any) => (
                  <tr key={item.id} className="border-b border-ember/10">
                    <td className="py-2">{item.user_id}</td>
                    <td className="py-2">{item.product}</td>
                    <td className="py-2">{item.stars}</td>
                    <td className="py-2">{item.eur}</td>
                    <td className="py-2">{item.date ? new Date(item.date).toLocaleString("de-DE") : "-"}</td>
                    <td className="py-2">{item.source}</td>
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
