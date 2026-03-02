"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchUsers } from "@/lib/api";

export default function UsersPage() {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useQuery({ queryKey: ["users"], queryFn: fetchUsers });

  const items = useMemo(() => {
    if (!data?.items) return [];
    if (!search.trim()) return data.items;
    const needle = search.toLowerCase();
    return data.items.filter((item: any) =>
      [item.username, item.first_name, String(item.id), String(item.telegram_user_id)]
        .filter(Boolean)
        .some((value: string) => value.toLowerCase().includes(needle)),
    );
  }, [data, search]);

  return (
    <main className="space-y-6 py-2">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">Users</h1>
        <p className="mt-2 text-sm text-ember/70">Пошук, статуси, streak і базові операції.</p>
      </header>

      <section className="surface rounded-2xl p-4">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Пошук user_id, telegram_id, username..."
          className="w-full rounded-xl border border-ember/20 bg-white px-3 py-2"
        />
      </section>

      <section className="surface overflow-x-auto rounded-2xl p-4">
        {isLoading || !data ? <p className="text-sm">Завантаження...</p> : null}
        {data ? (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-ember/20 text-left">
                <th className="py-2">ID</th>
                <th className="py-2">Username</th>
                <th className="py-2">Language</th>
                <th className="py-2">Streak</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item: any) => (
                <tr key={item.id} className="border-b border-ember/10">
                  <td className="py-2">{item.id}</td>
                  <td className="py-2">{item.username || "-"}</td>
                  <td className="py-2">{item.language}</td>
                  <td className="py-2">{item.streak}</td>
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
