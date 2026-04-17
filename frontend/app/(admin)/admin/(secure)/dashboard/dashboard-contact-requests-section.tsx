"use client";

import { REQUEST_STATUSES } from "./dashboard-config";
import {
  buildRequestSummary,
  formatRequestStatus,
  formatRequestType,
  getLongMessage,
} from "./dashboard-helpers";
import type { ContactRequestsData } from "./dashboard-types";

type DashboardContactRequestsSectionProps = {
  data: ContactRequestsData | undefined;
  isLoading: boolean;
  isStatusPending: boolean;
  activeRequestId: number | null;
  onStatusChange: (requestId: number, currentStatus: string, nextStatus: string) => void;
};

export function DashboardContactRequestsSection({
  data,
  isLoading,
  isStatusPending,
  activeRequestId,
  onStatusChange,
}: DashboardContactRequestsSectionProps) {
  return (
    <section className="surface rounded-2xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl">Anfragen von der Landing Page</h2>
        <p className="text-xs text-ember/60">{data ? `Gesamt: ${data.total}` : ""}</p>
      </div>

      {isLoading ? <p className="mt-3 text-sm">Anfragen werden geladen...</p> : null}

      {!isLoading && (!data || data.items.length === 0) ? (
        <p className="mt-3 text-sm text-emerald-700">Noch keine Anfragen vorhanden.</p>
      ) : null}

      <div className="mt-3 space-y-3">
        {data?.items.map((item) => {
          const isUpdating = isStatusPending && activeRequestId === item.id;
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
                      onStatusChange(item.id, item.status, event.target.value);
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
  );
}
