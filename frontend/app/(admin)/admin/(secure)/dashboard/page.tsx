"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchContactRequests, fetchOverview, updateContactRequestStatus } from "@/lib/api";

import { PERIOD_OPTIONS } from "./dashboard-config";
import { DashboardContactRequestsSection } from "./dashboard-contact-requests-section";
import { findPeakHourlyActivity, getMetric, mapFunnelStep, mapProductLabel } from "./dashboard-helpers";
import { DashboardOverviewSections } from "./dashboard-overview-sections";
import type {
  ContactRequestsData,
  FunnelChartItem,
  OverviewData,
  TopProductChartItem,
} from "./dashboard-types";

export default function DashboardPage() {
  const [period, setPeriod] = useState("7d");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<OverviewData>({
    queryKey: ["overview", period],
    queryFn: () => fetchOverview(period),
  });

  const { data: contactRequestsData, isLoading: isContactRequestsLoading } =
    useQuery<ContactRequestsData>({
      queryKey: ["contact-requests"],
      queryFn: fetchContactRequests,
    });

  const statusMutation = useMutation({
    mutationFn: ({ requestId, status }: { requestId: number; status: string }) =>
      updateContactRequestStatus(requestId, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["contact-requests"] });
    },
  });

  const funnelData = useMemo<FunnelChartItem[]>(() => {
    if (!data) {
      return [];
    }
    return data.funnel.map((item, index) => {
      const previousValue = index > 0 ? Number(data.funnel[index - 1]?.value ?? 0) : 0;
      const currentValue = Number(item.value ?? 0);
      const conversion =
        index === 0 ? 100 : previousValue > 0 ? (currentValue / previousValue) * 100 : 0;
      return {
        step: item.step,
        step_label: mapFunnelStep(item.step),
        value: currentValue,
        conversion_from_prev: conversion,
      };
    });
  }, [data]);

  const topProductsData = useMemo<TopProductChartItem[]>(() => {
    if (!data) {
      return [];
    }
    return data.top_products.map((item) => ({
      product: item.product,
      product_label: mapProductLabel(item.product),
      revenue_stars: Number(item.revenue_stars ?? 0),
    }));
  }, [data]);

  const totalRevenueStars = useMemo(() => {
    if (!data) {
      return 0;
    }
    return data.revenue_series.reduce((sum, item) => sum + Number(item.stars ?? 0), 0);
  }, [data]);

  const averageActiveUsers = useMemo(() => {
    if (!data || data.users_series.length === 0) {
      return 0;
    }
    const total = data.users_series.reduce((sum, item) => sum + Number(item.active_users ?? 0), 0);
    return total / data.users_series.length;
  }, [data]);

  const peakHourlyActivity = useMemo(
    () => findPeakHourlyActivity(data?.hourly_activity_series),
    [data],
  );

  const averageHourlyActivity = useMemo(() => {
    const series = data?.hourly_activity_series ?? [];
    if (series.length === 0) {
      return 0;
    }
    const total = series.reduce((sum, item) => sum + Number(item.active_users ?? 0), 0);
    return total / series.length;
  }, [data]);

  const topHourlyWindows = useMemo(() => {
    const series = data?.hourly_activity_series ?? [];
    return [...series]
      .filter((item) => Number(item.active_users ?? 0) > 0)
      .sort((left, right) => Number(right.active_users ?? 0) - Number(left.active_users ?? 0))
      .slice(0, 3);
  }, [data]);

  return (
    <main className="min-w-0 space-y-6 py-2">
      <header className="surface rounded-2xl p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-ember/60">Admin Übersicht</p>
            <h1 className="mt-1 text-3xl">Geschäftszahlen klar erklärt</h1>
            <p className="mt-2 text-sm text-ember/70">
              Alle Werte sind auf den gewählten Zeitraum bezogen und werden mit dem vorherigen
              gleich langen Zeitraum verglichen.
            </p>
            {data ? (
              <p className="mt-1 text-xs text-ember/60">
                Letzte Aktualisierung:{" "}
                {new Date(data.generated_at).toLocaleString("de-DE", {
                  timeZone: "Europe/Berlin",
                })}{" "}
                (Berlin)
              </p>
            ) : null}
          </div>
          <select
            value={period}
            onChange={(event) => setPeriod(event.target.value)}
            className="rounded-xl border border-ember/20 bg-white px-3 py-2"
          >
            {PERIOD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {isLoading || !data ? <p className="text-sm">Dashboard-Daten werden geladen...</p> : null}

      {data ? (
        <DashboardOverviewSections
          data={data}
          funnelData={funnelData}
          topProductsData={topProductsData}
          totalRevenueStars={totalRevenueStars}
          averageActiveUsers={averageActiveUsers}
          peakHourlyActivity={peakHourlyActivity}
          averageHourlyActivity={averageHourlyActivity}
          topHourlyWindows={topHourlyWindows}
        />
      ) : null}

      <DashboardContactRequestsSection
        data={contactRequestsData}
        isLoading={isContactRequestsLoading}
        isStatusPending={statusMutation.isPending}
        activeRequestId={statusMutation.variables?.requestId ?? null}
        onStatusChange={(requestId, currentStatus, nextStatus) => {
          if (nextStatus === currentStatus) {
            return;
          }
          statusMutation.mutate({ requestId, status: nextStatus });
        }}
      />
    </main>
  );
}
