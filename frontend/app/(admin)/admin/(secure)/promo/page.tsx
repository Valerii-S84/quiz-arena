"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, fetchPromo } from "@/lib/api";

type PromoItem = {
  id: string;
  code: string;
  type: string;
  value: number;
  product_id: string | null;
  max_uses: number;
  uses_count: number;
  valid_from: string;
  valid_until: string | null;
  channel_tag: string | null;
  status: string;
  created_at: string;
};

type PromoResponse = {
  items: PromoItem[];
  total: number;
  page: number;
  pages: number;
};

type MessageState = {
  kind: "success" | "error";
  text: string;
};

function formatPromoType(type: string, value: number): string {
  if (type === "discount_percent") {
    return `${value.toLocaleString("de-DE")} % Rabatt`;
  }
  if (type === "discount_stars") {
    return `${value.toLocaleString("de-DE")} Sterne Rabatt`;
  }
  if (type === "bonus_energy") {
    return `${value.toLocaleString("de-DE")} Energie Bonus`;
  }
  if (type === "bonus_subscription_days") {
    return `${value.toLocaleString("de-DE")} Premium-Tage`;
  }
  if (type === "free_product") {
    return "Gratis-Produkt";
  }
  return type;
}

function formatStatus(status: string): string {
  if (status === "active") {
    return "Aktiv";
  }
  if (status === "paused") {
    return "Pausiert";
  }
  if (status === "expired") {
    return "Abgelaufen";
  }
  if (status === "archived") {
    return "Archiviert";
  }
  return status;
}

function statusClass(status: string): string {
  if (status === "active") {
    return "border-emerald-300/70 bg-emerald-50 text-emerald-800";
  }
  if (status === "paused") {
    return "border-amber-300/70 bg-amber-50 text-amber-800";
  }
  if (status === "expired" || status === "archived") {
    return "border-ember/20 bg-white text-ember/80";
  }
  return "border-ember/20 bg-white text-ember/80";
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "Kein Enddatum";
  }
  return new Date(value).toLocaleString("de-DE");
}

export default function PromoPage() {
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [value, setValue] = useState("10");
  const [maxUses, setMaxUses] = useState("100");
  const [statusFilter, setStatusFilter] = useState("all");
  const [statusMessage, setStatusMessage] = useState<MessageState | null>(null);
  const { data, isLoading } = useQuery<PromoResponse>({
    queryKey: ["promo", statusFilter],
    queryFn: () => fetchPromo(statusFilter === "all" ? undefined : statusFilter),
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      await api.post("/admin/promo", {
        code: code.trim(),
        type: "discount_percent",
        value: Number(value),
        max_uses: Number(maxUses),
      });
    },
    onSuccess: async () => {
      setStatusMessage({ kind: "success", text: "Promocode wurde erstellt." });
      setCode("");
      await queryClient.invalidateQueries({ queryKey: ["promo"] });
    },
    onError: () => {
      setStatusMessage({
        kind: "error",
        text: "Promocode konnte nicht erstellt werden. Bitte Code oder Wert pruefen.",
      });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: async (promoId: string) => {
      await api.patch(`/admin/promo/${promoId}/toggle`);
    },
    onSuccess: async () => {
      setStatusMessage({ kind: "success", text: "Status wurde aktualisiert." });
      await queryClient.invalidateQueries({ queryKey: ["promo"] });
    },
    onError: () => {
      setStatusMessage({ kind: "error", text: "Status konnte nicht aktualisiert werden." });
    },
  });

  const totals = useMemo(() => {
    if (!data) {
      return { total: 0, active: 0, paused: 0, ended: 0 };
    }
    return {
      total: data.items.length,
      active: data.items.filter((item) => item.status === "active").length,
      paused: data.items.filter((item) => item.status === "paused").length,
      ended: data.items.filter((item) => item.status === "expired" || item.status === "archived").length,
    };
  }, [data]);

  function validateCreateForm(): boolean {
    setStatusMessage(null);
    if (code.trim().length < 4) {
      setStatusMessage({ kind: "error", text: "Code muss mindestens 4 Zeichen haben." });
      return false;
    }
    const parsedValue = Number(value);
    if (!Number.isFinite(parsedValue) || parsedValue <= 0 || parsedValue > 100) {
      setStatusMessage({ kind: "error", text: "Rabatt bitte zwischen 1 und 100 eingeben." });
      return false;
    }
    const parsedMaxUses = Number(maxUses);
    if (!Number.isInteger(parsedMaxUses) || parsedMaxUses < 1) {
      setStatusMessage({ kind: "error", text: "Maximale Nutzungen muessen mindestens 1 sein." });
      return false;
    }
    return true;
  }

  async function createPromo() {
    if (!validateCreateForm()) {
      return;
    }
    await createMutation.mutateAsync();
  }

  async function togglePromo(item: PromoItem) {
    if (item.status !== "active" && item.status !== "paused") {
      return;
    }
    setStatusMessage(null);
    await toggleMutation.mutateAsync(item.id);
  }

  return (
    <main className="space-y-6 py-2 fade-in">
      <header className="surface rounded-2xl p-5">
        <h1 className="text-3xl">Promo-Center</h1>
        <p className="mt-2 text-sm text-ember/70">
          Einfache Verwaltung fuer Rabattcodes: erstellen, pausieren und Nutzung verfolgen.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <article className="surface rounded-2xl p-4">
          <p className="text-xs uppercase tracking-wide text-ember/65">Codes gesamt</p>
          <p className="mt-2 text-3xl">{totals.total.toLocaleString("de-DE")}</p>
        </article>
        <article className="surface rounded-2xl p-4">
          <p className="text-xs uppercase tracking-wide text-ember/65">Aktiv</p>
          <p className="mt-2 text-3xl">{totals.active.toLocaleString("de-DE")}</p>
        </article>
        <article className="surface rounded-2xl p-4">
          <p className="text-xs uppercase tracking-wide text-ember/65">Pausiert</p>
          <p className="mt-2 text-3xl">{totals.paused.toLocaleString("de-DE")}</p>
        </article>
        <article className="surface rounded-2xl p-4">
          <p className="text-xs uppercase tracking-wide text-ember/65">Abgelaufen/Archiviert</p>
          <p className="mt-2 text-3xl">{totals.ended.toLocaleString("de-DE")}</p>
        </article>
      </section>

      <section className="surface rounded-2xl p-4">
        <h2 className="text-xl">Neuen Rabattcode erstellen</h2>
        <p className="mt-1 text-sm text-ember/70">Standard: Prozent-Rabatt fuer Shop-Produkte.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="Code (z.B. FRUEHLING10)"
            className="rounded-xl border border-ember/20 bg-white px-3 py-2"
          />
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Rabatt in %"
            className="rounded-xl border border-ember/20 bg-white px-3 py-2"
          />
          <input
            value={maxUses}
            onChange={(event) => setMaxUses(event.target.value)}
            placeholder="Max. Nutzungen"
            className="rounded-xl border border-ember/20 bg-white px-3 py-2"
          />
          <button
            onClick={() => void createPromo()}
            disabled={createMutation.isPending}
            className="rounded-xl bg-ember px-3 py-2 text-sand disabled:cursor-not-allowed disabled:opacity-70"
          >
            {createMutation.isPending ? "Wird erstellt..." : "Code erstellen"}
          </button>
          <a
            href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/admin/promo/export?format=csv`}
            className="rounded-xl border border-ember/20 px-3 py-2 text-center"
          >
            CSV exportieren
          </a>
        </div>
      </section>

      <section className="surface rounded-2xl p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            Statusfilter
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="mt-1 block rounded-xl border border-ember/20 bg-white px-3 py-2 text-sm"
            >
              <option value="all">Alle</option>
              <option value="active">Nur aktiv</option>
              <option value="paused">Nur pausiert</option>
              <option value="expired">Nur abgelaufen</option>
              <option value="archived">Nur archiviert</option>
            </select>
          </label>
        </div>
      </section>

      {statusMessage ? (
        <p className={`text-sm ${statusMessage.kind === "error" ? "text-red-700" : "text-emerald-700"}`}>
          {statusMessage.text}
        </p>
      ) : null}

      <section className="surface overflow-x-auto rounded-2xl p-4">
        <h2 className="text-xl">Alle Promo-Codes</h2>
        {isLoading || !data ? <p className="mt-3 text-sm">Daten werden geladen...</p> : null}
        {data ? (
          <table className="mt-4 min-w-full text-sm">
            <thead>
              <tr className="border-b border-ember/20 text-left">
                <th className="py-2">Code</th>
                <th className="py-2">Vorteil</th>
                <th className="py-2">Nutzung</th>
                <th className="py-2">Gueltig bis</th>
                <th className="py-2">Status</th>
                <th className="py-2 text-right">Aktion</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.id} className="border-b border-ember/10">
                  <td className="py-2 font-medium">{item.code}</td>
                  <td className="py-2">{formatPromoType(item.type, item.value)}</td>
                  <td className="py-2">
                    <p>
                      {item.uses_count.toLocaleString("de-DE")}/{item.max_uses.toLocaleString("de-DE")}
                    </p>
                    <div className="mt-1 h-2 w-28 rounded-full bg-ember/10">
                      <div
                        className="h-2 rounded-full bg-[#2f5f74]"
                        style={{
                          width: `${Math.min(100, (item.uses_count / Math.max(item.max_uses, 1)) * 100)}%`,
                        }}
                      />
                    </div>
                  </td>
                  <td className="py-2 text-xs text-ember/75">{formatDateTime(item.valid_until)}</td>
                  <td className="py-2">
                    <span className={`rounded-full border px-2 py-1 text-xs ${statusClass(item.status)}`}>
                      {formatStatus(item.status)}
                    </span>
                  </td>
                  <td className="py-2 text-right">
                    {item.status === "active" || item.status === "paused" ? (
                      <button
                        onClick={() => void togglePromo(item)}
                        disabled={toggleMutation.isPending}
                        className="rounded-lg border border-ember/20 px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-70"
                      >
                        {item.status === "active" ? "Pausieren" : "Aktivieren"}
                      </button>
                    ) : (
                      <span className="text-xs text-ember/55">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>
    </main>
  );
}
