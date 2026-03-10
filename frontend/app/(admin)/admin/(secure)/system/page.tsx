"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchSystemHealth } from "@/lib/api";

type ServiceStatus = {
  ok: boolean;
  workers?: string[];
  processed_updates_15m?: number;
};

type ErrorLogItem = {
  event_type: string;
  status: string;
  created_at: string;
};

type TopErrorItem = {
  type: string;
  count: number;
};

type LatencyItem = {
  date: string;
  p50: number | null;
  p95: number | null;
};

type SystemData = {
  services: Record<string, ServiceStatus>;
  error_log: ErrorLogItem[];
  top_10_errors: TopErrorItem[];
  queue_stats: {
    pending: number;
    failed: number;
  };
  api_latency: LatencyItem[];
};

const SERVICE_LABELS: Record<string, string> = {
  fastapi: "API",
  postgresql: "Datenbank",
  redis: "Redis Cache",
  celery: "Hintergrund-Worker",
  bot_webhook: "Telegram Webhook",
};

function formatServiceName(key: string): string {
  return SERVICE_LABELS[key] ?? key;
}

function statusText(ok: boolean): string {
  return ok ? "Stabil" : "Stoerung";
}

function statusClass(ok: boolean): string {
  return ok
    ? "border-emerald-300/70 bg-emerald-50 text-emerald-800"
    : "border-red-300/70 bg-red-50 text-red-800";
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("de-DE");
}

function formatErrorType(value: string): string {
  return value.replaceAll("_", " ");
}

function latencyState(p95: number | null): { label: string; className: string } {
  if (p95 === null) {
    return { label: "Keine Daten", className: "text-ember/70" };
  }
  if (p95 > 2000) {
    return { label: "Kritisch hoch", className: "text-red-700" };
  }
  if (p95 > 1000) {
    return { label: "Erhoeht", className: "text-amber-700" };
  }
  return { label: "Normal", className: "text-emerald-700" };
}

export default function SystemPage() {
  const { data, isLoading } = useQuery<SystemData>({
    queryKey: ["system"],
    queryFn: fetchSystemHealth,
  });

  const serviceEntries = useMemo(() => {
    if (!data) {
      return [];
    }
    return Object.entries(data.services).map(([key, value]) => ({
      key,
      value,
      label: formatServiceName(key),
    }));
  }, [data]);

  const downServices = useMemo(() => {
    return serviceEntries.filter((item) => !item.value.ok);
  }, [serviceEntries]);

  const latestLatency = useMemo(() => {
    if (!data || data.api_latency.length === 0) {
      return null;
    }
    for (let index = data.api_latency.length - 1; index >= 0; index -= 1) {
      const item = data.api_latency[index];
      if (item.p50 !== null || item.p95 !== null) {
        return item;
      }
    }
    return null;
  }, [data]);

  const latencyStatus = latencyState(latestLatency?.p95 ?? null);

  const topErrorTotal = useMemo(() => {
    if (!data) {
      return 0;
    }
    return data.top_10_errors.reduce((sum, row) => sum + row.count, 0);
  }, [data]);

  const workerCount = data?.services.celery?.workers?.length ?? 0;
  const webhookUpdates = data?.services.bot_webhook?.processed_updates_15m ?? 0;
  const servicesOkCount = serviceEntries.length - downServices.length;

  return (
    <main className="space-y-6 py-2 fade-in">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">Systemstatus</h1>
        <p className="mt-2 text-sm text-ember/70">
          Live-Ueberblick fuer Betrieb: Dienste, Warteschlangen, Fehler und API-Geschwindigkeit.
        </p>
      </header>

      {isLoading || !data ? <p className="text-sm">Daten werden geladen...</p> : null}

      {data ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Gesamtzustand</p>
              <p className={`mt-2 text-2xl ${downServices.length === 0 ? "text-emerald-700" : "text-red-700"}`}>
                {downServices.length === 0 ? "Stabil" : "Achtung"}
              </p>
              <p className="mt-1 text-xs text-ember/70">
                {servicesOkCount}/{serviceEntries.length} Dienste verfuegbar
              </p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Queue</p>
              <p className="mt-2 text-2xl">{data.queue_stats.pending.toLocaleString("de-DE")} wartend</p>
              <p className="mt-1 text-xs text-ember/70">
                {data.queue_stats.failed.toLocaleString("de-DE")} fehlgeschlagen
              </p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Webhook Aktivitaet (15m)</p>
              <p className="mt-2 text-2xl">{webhookUpdates.toLocaleString("de-DE")}</p>
              <p className="mt-1 text-xs text-ember/70">Verarbeitete Telegram Updates</p>
            </article>
            <article className="surface rounded-2xl p-4">
              <p className="text-xs uppercase tracking-wide text-ember/65">Worker online</p>
              <p className="mt-2 text-2xl">{workerCount.toLocaleString("de-DE")}</p>
              <p className={`mt-1 text-xs ${latencyStatus.className}`}>
                API p95: {latestLatency?.p95?.toLocaleString("de-DE") ?? "-"} ms ({latencyStatus.label})
              </p>
            </article>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Status der Dienste</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {serviceEntries.map(({ key, value, label }) => (
                <article key={key} className="rounded-xl border border-ember/15 bg-white/70 p-3 text-sm">
                  <p className="uppercase tracking-wide text-ember/60">{label}</p>
                  <p className="mt-2">
                    <span className={`rounded-full border px-2 py-1 text-xs ${statusClass(value.ok)}`}>
                      {statusText(value.ok)}
                    </span>
                  </p>
                  {key === "celery" ? (
                    <p className="mt-2 text-xs text-ember/75">
                      Worker: {(value.workers?.length ?? 0).toLocaleString("de-DE")}
                    </p>
                  ) : null}
                  {key === "bot_webhook" ? (
                    <p className="mt-2 text-xs text-ember/75">
                      Updates (15m): {(value.processed_updates_15m ?? 0).toLocaleString("de-DE")}
                    </p>
                  ) : null}
                  {!value.ok ? (
                    <p className="mt-2 text-xs text-red-700">Bitte Logs und Runtime-Status pruefen.</p>
                  ) : null}
                </article>
              ))}
            </div>
            {downServices.length > 0 ? (
              <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                Aktuelle Stoerung bei: {downServices.map((item) => item.label).join(", ")}.
              </div>
            ) : (
              <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                Alle Kern-Dienste laufen stabil.
              </div>
            )}
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Queue-Status</h2>
              <p className="mt-2 text-sm">Wartend: {data.queue_stats.pending.toLocaleString("de-DE")}</p>
              <p className="text-sm">Fehlgeschlagen: {data.queue_stats.failed.toLocaleString("de-DE")}</p>
              {data.queue_stats.failed > 0 ? (
                <p className="mt-3 text-sm text-red-700">
                  Fehlgeschlagene Jobs vorhanden. Worker-Log und Retry-Flow pruefen.
                </p>
              ) : (
                <p className="mt-3 text-sm text-emerald-700">Keine fehlgeschlagenen Jobs im Moment.</p>
              )}
              {data.queue_stats.pending > 200 ? (
                <p className="mt-1 text-sm text-amber-700">
                  Queue ist hoch. Bei Bedarf Worker-Skalierung erhoehen.
                </p>
              ) : null}
            </article>

            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">API-Latenz (p50/p95)</h2>
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
              <p className={`mt-3 text-sm ${latencyStatus.className}`}>
                Letzter p95-Wert: {latestLatency?.p95?.toLocaleString("de-DE") ?? "-"} ms ({latencyStatus.label})
              </p>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Top Fehler (24h)</h2>
              <div className="mt-3 space-y-2 text-sm">
                {data.top_10_errors.map((row) => {
                  const percent = topErrorTotal > 0 ? (row.count / topErrorTotal) * 100 : 0;
                  return (
                    <div key={row.type} className="rounded-lg border border-ember/15 bg-white/70 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <p>{formatErrorType(row.type)}</p>
                        <p className="text-xs text-ember/70">{row.count.toLocaleString("de-DE")}</p>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-ember/10">
                        <div
                          className="h-2 rounded-full bg-[#2f5f74]"
                          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
                {data.top_10_errors.length === 0 ? (
                  <p className="text-sm text-emerald-700">Keine Fehler im aktuellen Zeitraum.</p>
                ) : null}
              </div>
            </article>

            <article className="surface rounded-2xl p-4">
              <h2 className="text-xl">Letzte Outbox-Fehler</h2>
              <div className="mt-3 space-y-2 text-sm">
                {data.error_log.slice(0, 15).map((item) => (
                  <div key={`${item.event_type}-${item.created_at}`} className="rounded-lg border border-ember/15 bg-white/70 px-3 py-2">
                    <p>{formatErrorType(item.event_type)}</p>
                    <p className="mt-1 text-xs text-ember/70">
                      {item.status} • {formatDateTime(item.created_at)}
                    </p>
                  </div>
                ))}
                {data.error_log.length === 0 ? (
                  <p className="text-sm text-emerald-700">Keine Outbox-Fehler in den letzten 24 Stunden.</p>
                ) : null}
              </div>
            </article>
          </section>

          <section className="surface rounded-2xl p-4">
            <h2 className="text-xl">Empfohlene Routinechecks</h2>
            <div className="mt-3 grid gap-2 text-sm text-ember/85">
              <p>1. Bei Queue-Fehlern zuerst `worker` Logs pruefen.</p>
              <p>2. Bei hoher p95-Latenz Datenbank-Load und externe API-Limits kontrollieren.</p>
              <p>3. Wenn Webhook-Updates auf 0 fallen, Telegram Webhook und Redis-Verbindung testen.</p>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
