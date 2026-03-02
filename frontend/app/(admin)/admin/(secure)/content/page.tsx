"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchContentHealth } from "@/lib/api";

export default function ContentPage() {
  const { data, isLoading } = useQuery({ queryKey: ["content"], queryFn: fetchContentHealth });

  return (
    <main className="space-y-6 py-2">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">Content / Quiz Health</h1>
      </header>

      {isLoading || !data ? <p className="text-sm">Завантаження...</p> : null}

      {data ? (
        <>
          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Levels</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {data.level_stats.map((item: any) => (
                <article key={item.level} className="rounded-xl border border-ember/15 p-3">
                  <p className="text-sm uppercase tracking-wide text-ember/60">{item.level}</p>
                  <p className="mt-1 text-2xl">{item.total_questions}</p>
                  <p className="text-xs text-ember/70">Coverage: {item.coverage_percent}%</p>
                </article>
              ))}
            </div>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Flagged Questions</h2>
            <div className="mt-3 space-y-2 text-sm">
              {data.flagged_questions.map((item: any) => (
                <div key={item.id} className="rounded-lg border border-ember/15 bg-white/70 px-3 py-2">
                  #{item.id} • {item.reason} • user {item.user_id}
                </div>
              ))}
              {data.flagged_questions.length === 0 ? <p>Немає flagged items.</p> : null}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
