import {
  formatPromoDateTime,
  formatPromoDiscount,
  formatPromoProducts,
  promoStatusTotalLabel,
} from "./promo-view-model";
import type {
  AdminSession,
  PromoAuditResponse,
  PromoDetailTab,
  PromoItem,
  PromoProduct,
  PromoStatsResponse,
} from "./promo-types";

const DETAIL_TABS: Array<{ id: PromoDetailTab; label: string }> = [
  { id: "params", label: "Parameter" },
  { id: "stats", label: "Statistik" },
  { id: "audit", label: "Audit" },
];

const PROMO_TOTAL_STATUSES = ["APPLIED", "RESERVED", "EXPIRED", "REVOKED"] as const;

type PromoDetailPanelProps = {
  promoId: number;
  detailTab: PromoDetailTab;
  detail: PromoItem | undefined;
  stats: PromoStatsResponse | undefined;
  audit: PromoAuditResponse | undefined;
  products: PromoProduct[] | undefined;
  session: AdminSession | undefined;
  revealedCode: string | null;
  onClose: () => void;
  onChangeTab: (tab: PromoDetailTab) => void;
  onRevealCode: (promoId: number) => void;
  onCopyRevealedCode: (value: string) => void;
  onEdit: (item: PromoItem) => void;
  onToggle: (promoId: number) => void;
  onRevoke: (promoId: number) => void;
};

export function PromoDetailPanel({
  promoId,
  detailTab,
  detail,
  stats,
  audit,
  products,
  session,
  revealedCode,
  onClose,
  onChangeTab,
  onRevealCode,
  onCopyRevealedCode,
  onEdit,
  onToggle,
  onRevoke,
}: PromoDetailPanelProps) {
  return (
    <div className="fixed inset-y-0 right-0 z-30 w-full max-w-xl border-l border-white/60 bg-[linear-gradient(180deg,#fff8ed,rgba(244,238,228,0.98))] p-5 shadow-2xl">
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.26em] text-ember/55">Details</p>
            <h2 className="mt-2 text-3xl">{detail?.campaign_name || "Promo-Code"}</h2>
            <p className="mt-2 font-mono text-sm tracking-[0.18em]">{detail?.code}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-ember/15 px-3 py-1 text-sm"
          >
            Schließen
          </button>
        </div>

        {session?.role === "super_admin" && detail?.can_reveal_code ? (
          <div className="mt-4 rounded-2xl border border-amber-300/60 bg-amber-50 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => onRevealCode(promoId)}
                className="rounded-xl border border-ember/15 bg-white px-3 py-2 text-sm"
              >
                Vollständigen Code anzeigen
              </button>
              {revealedCode ? (
                <button
                  type="button"
                  onClick={() => onCopyRevealedCode(revealedCode)}
                  className="rounded-xl border border-ember/15 bg-white px-3 py-2 text-sm"
                >
                  Kopieren
                </button>
              ) : null}
            </div>
            {revealedCode ? (
              <div className="mt-3 rounded-2xl bg-white px-4 py-3 font-mono text-lg tracking-[0.24em]">
                {revealedCode}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="mt-5 flex gap-2">
          {DETAIL_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onChangeTab(tab.id)}
              className={`rounded-full px-4 py-2 text-sm ${
                detailTab === tab.id
                  ? "bg-ember text-sand"
                  : "border border-ember/15 bg-white"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="mt-5 flex-1 overflow-y-auto rounded-[28px] border border-ember/10 bg-white/70 p-4">
          {detailTab === "params" ? (
            <div className="grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Rabatt</p>
                <p className="mt-2">{detail ? formatPromoDiscount(detail) : "..."}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Produkte</p>
                <p className="mt-2">
                  {detail ? formatPromoProducts(detail.applicable_products, products) : "..."}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Gültig ab</p>
                <p className="mt-2">
                  {detail ? formatPromoDateTime(detail.valid_from) : "..."}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Gültig bis</p>
                <p className="mt-2">
                  {detail ? formatPromoDateTime(detail.valid_until) : "..."}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-ember/50">Max. gesamt</p>
                <p className="mt-2">{detail?.max_total_uses ?? 0}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-ember/50">
                  Max. pro Nutzer
                </p>
                <p className="mt-2">{detail?.max_per_user ?? 1}</p>
              </div>
            </div>
          ) : null}

          {detailTab === "stats" ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <article className="rounded-2xl border border-emerald-200/70 bg-emerald-50 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-emerald-700">Genutzt</p>
                  <p className="mt-2 text-3xl">{stats?.used_total ?? 0}</p>
                </article>
                <article className="rounded-2xl border border-amber-200/70 bg-amber-50 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-amber-700">
                    Aktive Reservierungen
                  </p>
                  <p className="mt-2 text-3xl">{stats?.reserved_active ?? 0}</p>
                </article>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {PROMO_TOTAL_STATUSES.map((status) => (
                  <article key={status} className="rounded-2xl border border-ember/10 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-ember/55">
                      {promoStatusTotalLabel(status)}
                    </p>
                    <p className="mt-2 text-2xl">{stats?.status_totals?.[status] ?? 0}</p>
                  </article>
                ))}
              </div>
              <div className="overflow-x-auto rounded-2xl border border-ember/10">
                <table className="min-w-full text-sm">
                  <thead className="border-b border-ember/10 bg-[#f8efe1] text-left">
                    <tr>
                      <th className="px-3 py-3">Nutzer</th>
                      <th className="px-3 py-3">Zeit</th>
                      <th className="px-3 py-3">Status</th>
                      <th className="px-3 py-3">Produkt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats?.redemptions.map((item) => (
                      <tr
                        key={`${item.user_id}-${item.redeemed_at}`}
                        className="border-b border-ember/10 last:border-b-0"
                      >
                        <td className="px-3 py-3">{item.user_id}</td>
                        <td className="px-3 py-3">{formatPromoDateTime(item.redeemed_at)}</td>
                        <td className="px-3 py-3">{item.status}</td>
                        <td className="px-3 py-3">{item.product_id ?? "Noch offen"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}

          {detailTab === "audit" ? (
            <div className="space-y-3">
              {audit?.items.map((item) => (
                <article key={item.id} className="rounded-2xl border border-ember/10 bg-white px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium">{item.action}</p>
                    <p className="text-xs text-ember/55">{formatPromoDateTime(item.created_at)}</p>
                  </div>
                  <p className="mt-2 text-sm text-ember/70">{item.admin}</p>
                </article>
              ))}
            </div>
          ) : null}
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {detail ? (
            <button
              type="button"
              onClick={() => onEdit(detail)}
              className="rounded-2xl border border-ember/15 px-4 py-3 text-sm"
            >
              Bearbeiten
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => onToggle(promoId)}
            className="rounded-2xl border border-ember/15 px-4 py-3 text-sm"
          >
            {detail?.status === "active" ? "Deaktivieren" : "Aktivieren"}
          </button>
          <button
            type="button"
            onClick={() => onRevoke(promoId)}
            className="rounded-2xl bg-ember px-4 py-3 text-sm text-sand"
          >
            Widerrufen
          </button>
        </div>
      </div>
    </div>
  );
}
