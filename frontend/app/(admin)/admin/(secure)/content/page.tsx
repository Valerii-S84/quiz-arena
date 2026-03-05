"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchContentHealth } from "@/lib/api";

const MODE_LABELS: Record<string, string> = {
  ARTIKEL_SPRINT: "Artikel Sprint",
  QUICK_MIX_A1A2: "Quick Mix A1-A2",
  DAILY_CHALLENGE: "Daily Challenge",
  TOURNAMENT: "Turnier",
};

const LEVEL_ORDER: Record<string, number> = {
  A1: 1,
  A2: 2,
  B1: 3,
  B2: 4,
  C1: 5,
  C2: 6,
};

type LevelStat = {
  level: string;
  total_questions: number;
  attempts: number;
  coverage_percent: number;
};

type FlaggedQuestion = {
  id: number;
  user_id: number;
  reason: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type GrammarPipeline = {
  status: string;
  updated_at: string | null;
  payload: Record<string, unknown>;
};

type DuplicateItem = {
  question_text: string;
  count: number;
};

type ModeLevelDistributionItem = {
  mode_code: string;
  level: string;
  attempts: number;
  percent_in_mode: number;
  percent_of_all_attempts: number;
};

type ContentHealthData = {
  level_stats: LevelStat[];
  flagged_questions: FlaggedQuestion[];
  grammar_pipeline: GrammarPipeline;
  duplicates: DuplicateItem[];
  mode_level_distribution: ModeLevelDistributionItem[];
};

function formatModeLabel(modeCode: string): string {
  return MODE_LABELS[modeCode] ?? modeCode.replaceAll("_", " ");
}

function formatReason(reason: string): string {
  if (reason === "question_flagged") {
    return "Unklare Frage gemeldet";
  }
  if (reason === "question_duplicate") {
    return "Doppelte Frage gemeldet";
  }
  if (reason === "grammar_flagged") {
    return "Grammatikproblem gemeldet";
  }
  return reason;
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("de-DE");
}

function formatStatus(status: string): string {
  if (status === "ok" || status === "healthy") {
    return "Stabil";
  }
  if (status === "running") {
    return "Läuft";
  }
  if (status === "warning") {
    return "Warnung";
  }
  if (status === "error" || status === "failed") {
    return "Fehler";
  }
  if (status === "unknown") {
    return "Unbekannt";
  }
  return status;
}

function statusBadgeClass(status: string): string {
  if (status === "ok" || status === "healthy" || status === "running") {
    return "border-emerald-300/70 bg-emerald-50 text-emerald-800";
  }
  if (status === "warning") {
    return "border-amber-300/70 bg-amber-50 text-amber-800";
  }
  if (status === "error" || status === "failed") {
    return "border-red-300/70 bg-red-50 text-red-800";
  }
  return "border-ember/20 bg-white text-ember/80";
}

function toDisplayText(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value === null) {
    return "null";
  }
  return JSON.stringify(value) ?? String(value);
}

export default function ContentPage() {
  const { data, isLoading } = useQuery<ContentHealthData>({
    queryKey: ["content"],
    queryFn: fetchContentHealth,
  });

  const totals = useMemo(() => {
    if (!data) {
      return {
        totalQuestions: 0,
        totalAttempts: 0,
      };
    }
    return {
      totalQuestions: data.level_stats.reduce((sum, item) => sum + item.total_questions, 0),
      totalAttempts: data.level_stats.reduce((sum, item) => sum + item.attempts, 0),
    };
  }, [data]);

  const sortedLevelStats = useMemo(() => {
    if (!data) {
      return [];
    }
    return [...data.level_stats].sort((a, b) => {
      const left = LEVEL_ORDER[a.level.toUpperCase()] ?? 99;
      const right = LEVEL_ORDER[b.level.toUpperCase()] ?? 99;
      return left - right;
    });
  }, [data]);

  const groupedDistribution = useMemo(() => {
    if (!data) {
      return [];
    }
    const grouped = new Map<string, ModeLevelDistributionItem[]>();
    for (const item of data.mode_level_distribution) {
      const previous = grouped.get(item.mode_code) ?? [];
      previous.push(item);
      grouped.set(item.mode_code, previous);
    }
    return Array.from(grouped.entries())
      .map(([modeCode, rows]) => {
        const sortedRows = [...rows].sort((a, b) => {
          const left = LEVEL_ORDER[a.level.toUpperCase()] ?? 99;
          const right = LEVEL_ORDER[b.level.toUpperCase()] ?? 99;
          return left - right;
        });
        const totalAttempts = sortedRows.reduce((sum, row) => sum + row.attempts, 0);
        return {
          modeCode,
          modeLabel: formatModeLabel(modeCode),
          totalAttempts,
          rows: sortedRows,
        };
      })
      .sort((a, b) => b.totalAttempts - a.totalAttempts);
  }, [data]);

  const grammarPayload = useMemo(() => {
    if (!data) {
      return [];
    }
    return Object.entries(data.grammar_pipeline.payload).slice(0, 6);
  }, [data]);

  return (
    <main className="space-y-6 py-2 fade-in">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">Inhalte & Qualitaet</h1>
        <p className="mt-2 text-sm text-ember/70">
          Einfache Uebersicht: Welche Niveaus genutzt werden, wo Engpaesse liegen und was auffaellig ist.
        </p>
      </header>

      {isLoading || !data ? <p className="text-sm">Daten werden geladen...</p> : null}

      {data ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Fragen gesamt</p>
              <p className="mt-2 text-3xl">{totals.totalQuestions.toLocaleString("de-DE")}</p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Antworten gesamt</p>
              <p className="mt-2 text-3xl">{totals.totalAttempts.toLocaleString("de-DE")}</p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Gemeldete Fragen</p>
              <p className="mt-2 text-3xl">{data.flagged_questions.length.toLocaleString("de-DE")}</p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Doppelte Fragen</p>
              <p className="mt-2 text-3xl">{data.duplicates.length.toLocaleString("de-DE")}</p>
            </article>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Fragenbestand nach Niveau</h2>
            <p className="mt-1 text-sm text-ember/70">
              Zeigt, wie gross jede CEFR-Stufe ist und wie stark sie bisher gespielt wurde.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {sortedLevelStats.map((item) => (
                <article key={item.level} className="rounded-xl border border-ember/15 bg-white/70 p-3">
                  <p className="text-xs uppercase tracking-wide text-ember/65">{item.level}</p>
                  <p className="mt-1 text-2xl">{item.total_questions.toLocaleString("de-DE")} Fragen</p>
                  <p className="mt-1 text-sm text-ember/80">
                    {item.attempts.toLocaleString("de-DE")} Antworten
                  </p>
                  <p className="mt-2 text-xs text-ember/70">
                    Abdeckung: {item.coverage_percent.toLocaleString("de-DE")}%
                  </p>
                  <div className="mt-1 h-2 rounded-full bg-ember/10">
                    <div
                      className="h-2 rounded-full bg-[#3f6f86]"
                      style={{ width: `${Math.min(100, Math.max(0, item.coverage_percent))}%` }}
                    />
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Nutzung nach Modus und Niveau</h2>
            <p className="mt-1 text-sm text-ember/70">
              Beispiel: In welchem Anteil Artikel Sprint auf B1 gespielt wurde.
            </p>
            {groupedDistribution.length === 0 ? (
              <p className="mt-3 text-sm text-ember/75">Noch keine Antworten in den Daten vorhanden.</p>
            ) : (
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {groupedDistribution.map((modeBlock) => (
                  <article key={modeBlock.modeCode} className="rounded-xl border border-ember/15 bg-white/70 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-lg">{modeBlock.modeLabel}</h3>
                      <p className="text-xs text-ember/70">
                        {modeBlock.totalAttempts.toLocaleString("de-DE")} Antworten
                      </p>
                    </div>
                    <div className="mt-3 space-y-2">
                      {modeBlock.rows.map((row) => (
                        <div key={`${modeBlock.modeCode}-${row.level}`}>
                          <div className="flex items-center justify-between text-xs text-ember/80">
                            <span>{row.level}</span>
                            <span>
                              {row.attempts.toLocaleString("de-DE")} Antworten •{" "}
                              {row.percent_in_mode.toLocaleString("de-DE")}%
                            </span>
                          </div>
                          <div className="mt-1 h-2 rounded-full bg-ember/10">
                            <div
                              className="h-2 rounded-full bg-[#2f5f74]"
                              style={{ width: `${Math.min(100, Math.max(0, row.percent_in_mode))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Grammatik-Pipeline</h2>
              <div className="mt-3 flex items-center gap-2">
                <span
                  className={`rounded-full border px-2 py-1 text-xs ${statusBadgeClass(data.grammar_pipeline.status)}`}
                >
                  {formatStatus(data.grammar_pipeline.status)}
                </span>
                <span className="text-xs text-ember/70">
                  Aktualisiert: {formatDateTime(data.grammar_pipeline.updated_at)}
                </span>
              </div>
              {grammarPayload.length > 0 ? (
                <div className="mt-3 space-y-1 text-sm text-ember/80">
                  {grammarPayload.map(([key, value]) => (
                    <p key={key}>
                      {key}: {toDisplayText(value)}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-sm text-ember/75">Keine Zusatzdetails vorhanden.</p>
              )}
            </article>

            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Moegliche Duplikate</h2>
              <div className="mt-3 space-y-2 text-sm">
                {data.duplicates.slice(0, 8).map((item) => (
                  <div key={item.question_text} className="rounded-lg border border-ember/15 bg-white/70 px-3 py-2">
                    <p className="line-clamp-2 text-ember/85">{item.question_text}</p>
                    <p className="mt-1 text-xs text-ember/70">{item.count} Vorkommen</p>
                  </div>
                ))}
                {data.duplicates.length === 0 ? <p className="text-ember/75">Keine Duplikate erkannt.</p> : null}
              </div>
            </article>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Neueste Meldungen aus der Community</h2>
            <div className="mt-3 space-y-2 text-sm">
              {data.flagged_questions.slice(0, 15).map((item) => (
                <div key={item.id} className="rounded-lg border border-ember/15 bg-white/70 px-3 py-2">
                  <p>
                    #{item.id} • {formatReason(item.reason)} • Nutzer {item.user_id}
                  </p>
                  <p className="mt-1 text-xs text-ember/70">{formatDateTime(item.created_at)}</p>
                </div>
              ))}
              {data.flagged_questions.length === 0 ? (
                <p className="text-sm text-ember/75">Aktuell liegen keine Meldungen vor.</p>
              ) : null}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
