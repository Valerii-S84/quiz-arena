"use client";

import { useDeferredValue, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchUsers, type UserListSortBy } from "@/lib/api";

const PAGE_SIZE = 100;

const VIEW_OPTIONS = [
  {
    value: "created_at",
    label: "Neueste zuerst",
    hint: "Neue Registrierungen und letzte Aktivitaet im Fokus.",
  },
  {
    value: "daily_challenge_rating",
    label: "Daily Challenge Ranking",
    hint: "Sortiert nach Gesamtpunkten aus abgeschlossenen Daily Challenges.",
  },
] as const satisfies ReadonlyArray<{
  value: UserListSortBy;
  label: string;
  hint: string;
}>;

type UserItem = {
  id: number;
  telegram_user_id: number;
  username: string | null;
  first_name: string | null;
  language: string | null;
  status: string;
  created_at: string;
  last_seen_at: string | null;
  streak: number;
  daily_challenge_score: number;
  daily_challenge_completed_runs: number;
};

type UsersData = {
  items: UserItem[];
  total: number;
  page: number;
  pages: number;
};

function formatDateTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("de-DE");
}

function formatDisplayName(item: UserItem): string {
  if (item.username) {
    return `@${item.username}`;
  }
  if (item.first_name) {
    return item.first_name;
  }
  return `Nutzer ${item.id}`;
}

function statusBadgeClass(status: string): string {
  if (status === "ACTIVE") {
    return "border-emerald-300/70 bg-emerald-50 text-emerald-800";
  }
  if (status === "BLOCKED") {
    return "border-red-300/70 bg-red-50 text-red-800";
  }
  return "border-ember/20 bg-white text-ember/80";
}

export default function UsersPage() {
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<UserListSortBy>("created_at");
  const deferredSearch = useDeferredValue(searchInput.trim());

  const { data, isLoading, isFetching } = useQuery<UsersData>({
    queryKey: ["users", page, deferredSearch, sortBy],
    queryFn: () =>
      fetchUsers({
        page,
        limit: PAGE_SIZE,
        search: deferredSearch,
        sortBy,
      }),
    placeholderData: (previousData) => previousData,
  });

  const items = useMemo(() => data?.items ?? [], [data]);
  const pageSummary = useMemo(() => {
    if (!data || data.total === 0) {
      return { from: 0, to: 0 };
    }
    return {
      from: (data.page - 1) * PAGE_SIZE + 1,
      to: Math.min(data.total, data.page * PAGE_SIZE),
    };
  }, [data]);
  const pageMaxDailyScore = useMemo(
    () => Math.max(1, ...items.map((item) => item.daily_challenge_score)),
    [items],
  );
  const topRankedUser = items[0] ?? null;
  const averageDailyScore = useMemo(() => {
    if (!items.length) {
      return 0;
    }
    return Math.round(
      items.reduce((sum, item) => sum + item.daily_challenge_score, 0) / items.length,
    );
  }, [items]);

  return (
    <main className="min-w-0 space-y-6 py-2 fade-in">
      <header className="surface rounded-[28px] p-6">
        <h1 className="text-3xl">Nutzer</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ember/70">
          Alle Nutzer in einer breiteren, paginierten Ansicht mit 100 Eintraegen pro Seite.
          Zusetzlich gibt es einen eigenen Modus fuer das Daily-Challenge-Ranking.
        </p>
      </header>

      <section className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)]">
        <article className="surface min-w-0 rounded-[28px] p-5">
          <div className="flex flex-col gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-ember/45">
                Suche
              </p>
              <input
                value={searchInput}
                onChange={(event) => {
                  setSearchInput(event.target.value);
                  setPage(1);
                }}
                placeholder="Suche nach user_id, telegram_id, username oder Vorname..."
                className="mt-3 w-full rounded-2xl border border-ember/15 bg-white px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] outline-none transition focus:border-[#295065]/35 focus:ring-2 focus:ring-[#295065]/15"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <div className="rounded-2xl border border-ember/12 bg-[#fff9f3] p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-ember/45">Gesamt</p>
                <p className="mt-2 text-2xl font-semibold text-[#1f4257]">
                  {data?.total.toLocaleString("de-DE") ?? "0"}
                </p>
                <p className="mt-1 text-xs text-ember/60">Registrierte Nutzer</p>
              </div>
              <div className="rounded-2xl border border-[#295065]/10 bg-[linear-gradient(135deg,rgba(41,80,101,0.08),rgba(137,245,199,0.16))] p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-ember/45">Seite</p>
                <p className="mt-2 text-2xl font-semibold text-[#1f4257]">
                  {pageSummary.from}-{pageSummary.to}
                </p>
                <p className="mt-1 text-xs text-ember/60">von {data?.total ?? 0} Nutzern</p>
              </div>
              <div className="rounded-2xl border border-[#89f5c7]/30 bg-[linear-gradient(135deg,rgba(137,245,199,0.18),rgba(255,255,255,0.92))] p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-ember/45">
                  {sortBy === "daily_challenge_rating" ? "Top-Score" : "Schnitt Daily"}
                </p>
                <p className="mt-2 text-2xl font-semibold text-[#1f4257]">
                  {sortBy === "daily_challenge_rating"
                    ? (topRankedUser?.daily_challenge_score ?? 0).toLocaleString("de-DE")
                    : averageDailyScore.toLocaleString("de-DE")}
                </p>
                <p className="mt-1 text-xs text-ember/60">
                  {sortBy === "daily_challenge_rating"
                    ? "Punkte des sichtbaren Spitzenplatzes"
                    : "Durchschnittliche Punkte auf der aktuellen Seite"}
                </p>
              </div>
            </div>
          </div>
        </article>

        <article className="surface min-w-0 rounded-[28px] p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-ember/45">
            Ansicht
          </p>
          <div className="mt-4 space-y-3">
            {VIEW_OPTIONS.map((option) => {
              const isActive = option.value === sortBy;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    setSortBy(option.value);
                    setPage(1);
                  }}
                  className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                    isActive
                      ? "border-[#295065]/20 bg-[linear-gradient(135deg,rgba(41,80,101,0.12),rgba(137,245,199,0.16))] shadow-[0_14px_34px_rgba(41,80,101,0.12)]"
                      : "border-ember/12 bg-white hover:border-[#295065]/16 hover:bg-[#fffaf5]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-semibold text-[#1f4257]">{option.label}</p>
                      <p className="mt-1 text-sm text-ember/65">{option.hint}</p>
                    </div>
                    <span
                      className={`inline-flex h-6 min-w-6 items-center justify-center rounded-full px-2 text-xs font-semibold ${
                        isActive ? "bg-[#1f4257] text-white" : "bg-ember/10 text-ember/65"
                      }`}
                    >
                      {isActive ? "Aktiv" : "Aus"}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </article>
      </section>

      <section className="surface min-w-0 overflow-hidden rounded-[28px] p-0">
        <div className="flex flex-col gap-3 border-b border-ember/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-semibold text-[#1f4257]">
              {sortBy === "daily_challenge_rating"
                ? "Daily-Challenge-Ranking aller Nutzer"
                : "Alle Nutzer nach Registrierung"}
            </p>
            <p className="mt-1 text-xs text-ember/60">
              100 Nutzer pro Seite. Suche und Sortierung laufen serverseitig.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={!data || data.page <= 1}
              className="rounded-xl border border-ember/15 bg-white px-3 py-2 text-ember/80 transition hover:border-[#295065]/20 hover:text-[#1f4257] disabled:cursor-not-allowed disabled:opacity-45"
            >
              Zurueck
            </button>
            <span className="rounded-xl bg-[#fff7ef] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-ember/55">
              Seite {data?.page ?? page} / {data?.pages ?? 1}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => current + 1)}
              disabled={!data || data.page >= data.pages}
              className="rounded-xl border border-ember/15 bg-white px-3 py-2 text-ember/80 transition hover:border-[#295065]/20 hover:text-[#1f4257] disabled:cursor-not-allowed disabled:opacity-45"
            >
              Weiter
            </button>
          </div>
        </div>

        {isLoading && !data ? <p className="px-5 py-5 text-sm">Daten werden geladen...</p> : null}
        {data ? (
          <div className="max-w-full overflow-x-auto">
            <table className="w-full min-w-[72rem] text-sm">
              <thead className="bg-[#fff8f0] text-left">
                <tr className="border-b border-ember/12">
                  <th className="px-5 py-3 font-medium text-ember/65">#</th>
                  <th className="px-5 py-3 font-medium text-ember/65">Nutzer</th>
                  <th className="px-5 py-3 font-medium text-ember/65">Sprache</th>
                  <th className="px-5 py-3 font-medium text-ember/65">Daily Challenge</th>
                  <th className="px-5 py-3 font-medium text-ember/65">Streak</th>
                  <th className="px-5 py-3 font-medium text-ember/65">Status</th>
                  <th className="px-5 py-3 font-medium text-ember/65">Zuletzt aktiv</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => {
                  const position = (page - 1) * PAGE_SIZE + index + 1;
                  const scoreWidth =
                    item.daily_challenge_score > 0
                      ? `${Math.max(
                          8,
                          Math.round((item.daily_challenge_score / pageMaxDailyScore) * 100),
                        )}%`
                      : "0%";

                  return (
                    <tr
                      key={item.id}
                      className="border-b border-ember/8 align-top transition hover:bg-[#fffdf9]"
                    >
                      <td className="px-5 py-4">
                        <div className="inline-flex min-w-10 items-center justify-center rounded-2xl bg-[#fff3e2] px-3 py-2 text-xs font-semibold text-[#1f4257]">
                          {position}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <div className="w-[17rem] min-w-[17rem]">
                          <p className="font-semibold text-[#1f4257]">{formatDisplayName(item)}</p>
                          <p className="mt-1 text-xs text-ember/60">
                            ID {item.id} · Telegram {item.telegram_user_id}
                          </p>
                          <p className="mt-2 text-xs text-ember/55">
                            Beigetreten {formatDateTime(item.created_at)}
                          </p>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span className="inline-flex rounded-full bg-ember/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-ember/70">
                          {item.language || "-"}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <div className="w-[14rem] min-w-[14rem]">
                          <div className="flex items-end justify-between gap-3">
                            <div>
                              <p className="text-lg font-semibold text-[#1f4257]">
                                {item.daily_challenge_score.toLocaleString("de-DE")}
                              </p>
                              <p className="text-xs text-ember/60">
                                {item.daily_challenge_completed_runs.toLocaleString("de-DE")}{" "}
                                abgeschlossene Runs
                              </p>
                            </div>
                            {sortBy === "daily_challenge_rating" ? (
                              <span className="rounded-full bg-[#1f4257] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-white">
                                Ranking
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-3 h-2 rounded-full bg-[#e8ddd1]">
                            <div
                              className="h-2 rounded-full bg-[linear-gradient(90deg,#295065,#89f5c7)]"
                              style={{ width: scoreWidth }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <div className="inline-flex rounded-2xl border border-[#89f5c7]/35 bg-[#f3fff9] px-3 py-2 font-semibold text-[#1f4257]">
                          {item.streak}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span
                          className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${statusBadgeClass(item.status)}`}
                        >
                          {item.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-ember/70">
                        <p>{formatDateTime(item.last_seen_at)}</p>
                        <p className="mt-1 text-xs text-ember/50">letzte bekannte Aktivitaet</p>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!items.length ? (
              <div className="px-5 py-10 text-center text-sm text-ember/65">
                Keine Nutzer fuer diese Filter gefunden.
              </div>
            ) : null}
          </div>
        ) : null}

        {isFetching && data ? (
          <div className="border-t border-ember/10 px-5 py-3 text-xs text-ember/55">
            Liste wird aktualisiert...
          </div>
        ) : null}
      </section>
    </main>
  );
}
