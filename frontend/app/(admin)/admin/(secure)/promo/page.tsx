"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, fetchPromo } from "@/lib/api";

export default function PromoPage() {
  const [code, setCode] = useState("");
  const [value, setValue] = useState("10");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const { data, isLoading, refetch } = useQuery({ queryKey: ["promo"], queryFn: fetchPromo });

  async function createPromo() {
    setStatusMessage(null);
    try {
      await api.post("/admin/promo", {
        code,
        type: "discount_percent",
        value: Number(value),
        max_uses: 100,
      });
      setStatusMessage("Промокод створено");
      setCode("");
      await refetch();
    } catch {
      setStatusMessage("Не вдалося створити промокод");
    }
  }

  return (
    <main className="space-y-6 py-2">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">Promo Codes</h1>
        <p className="mt-2 text-sm text-ember/70">CRUD, bulk generation, export and usages.</p>
      </header>

      <section className="surface grid gap-3 rounded-2xl p-4 sm:grid-cols-4">
        <input
          value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="Code"
          className="rounded-xl border border-ember/20 bg-white px-3 py-2"
        />
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Value"
          className="rounded-xl border border-ember/20 bg-white px-3 py-2"
        />
        <button onClick={createPromo} className="rounded-xl bg-ember px-3 py-2 text-sand">
          Create
        </button>
        <a
          href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/admin/promo/export?format=csv`}
          className="rounded-xl border border-ember/20 px-3 py-2 text-center"
        >
          Export CSV
        </a>
      </section>

      {statusMessage ? <p className="text-sm text-ember/80">{statusMessage}</p> : null}

      <section className="surface overflow-x-auto rounded-2xl p-4">
        {isLoading || !data ? <p className="text-sm">Завантаження...</p> : null}
        {data ? (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-ember/20 text-left">
                <th className="py-2">Code</th>
                <th className="py-2">Type</th>
                <th className="py-2">Value</th>
                <th className="py-2">Uses</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item: any) => (
                <tr key={item.id} className="border-b border-ember/10">
                  <td className="py-2">{item.code}</td>
                  <td className="py-2">{item.type}</td>
                  <td className="py-2">{item.value}</td>
                  <td className="py-2">
                    {item.uses_count}/{item.max_uses}
                  </td>
                  <td className="py-2">{item.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>
    </main>
  );
}
