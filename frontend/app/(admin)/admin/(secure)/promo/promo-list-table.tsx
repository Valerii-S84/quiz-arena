import {
  formatPromoDateTime,
  formatPromoDiscount,
  formatPromoProducts,
  formatPromoUsage,
  promoStatusClass,
  promoStatusLabel,
} from "./promo-view-model";
import type { PromoItem, PromoProduct } from "./promo-types";

type PromoListTableProps = {
  items: PromoItem[] | undefined;
  products: PromoProduct[] | undefined;
  isLoading: boolean;
  onOpenDetails: (promoId: number) => void;
  onOpenStats: (promoId: number) => void;
  onEdit: (item: PromoItem) => void;
  onToggle: (promoId: number) => void;
  onRevoke: (promoId: number) => void;
};

export function PromoListTable({
  items,
  products,
  isLoading,
  onOpenDetails,
  onOpenStats,
  onEdit,
  onToggle,
  onRevoke,
}: PromoListTableProps) {
  return (
    <section className="surface overflow-hidden rounded-[30px]">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="border-b border-ember/10 bg-[#f8efe1] text-left">
            <tr>
              <th className="px-4 py-4">Code</th>
              <th className="px-4 py-4">Kampagne</th>
              <th className="px-4 py-4">Rabatt</th>
              <th className="px-4 py-4">Produkte</th>
              <th className="px-4 py-4">Laufzeit</th>
              <th className="px-4 py-4">Nutzung</th>
              <th className="px-4 py-4">Status</th>
              <th className="px-4 py-4 text-right">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {items?.map((item) => (
              <tr
                key={item.id}
                className="cursor-pointer border-b border-ember/10 bg-white/55 transition hover:bg-[#fff8ea]"
                onClick={() => onOpenDetails(item.id)}
              >
                <td className="px-4 py-4 font-mono tracking-[0.18em]">{item.code}</td>
                <td className="px-4 py-4">
                  <p className="font-medium">{item.campaign_name || "Ohne Namen"}</p>
                  <p className="mt-1 text-xs text-ember/60">#{item.id}</p>
                </td>
                <td className="px-4 py-4">{formatPromoDiscount(item)}</td>
                <td className="px-4 py-4 text-xs text-ember/70">
                  {formatPromoProducts(item.applicable_products, products)}
                </td>
                <td className="px-4 py-4 text-xs text-ember/70">
                  <p>{formatPromoDateTime(item.valid_from)}</p>
                  <p className="mt-1">bis {formatPromoDateTime(item.valid_until)}</p>
                </td>
                <td className="px-4 py-4">{formatPromoUsage(item)}</td>
                <td className="px-4 py-4">
                  <span
                    className={`rounded-full border px-3 py-1 text-xs ${promoStatusClass(item.status)}`}
                  >
                    {promoStatusLabel(item.status)}
                  </span>
                </td>
                <td className="px-4 py-4">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onEdit(item);
                      }}
                      className="rounded-xl border border-ember/15 px-3 py-2 text-xs"
                    >
                      Bearbeiten
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenStats(item.id);
                      }}
                      className="rounded-xl border border-ember/15 px-3 py-2 text-xs"
                    >
                      Statistik
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onToggle(item.id);
                      }}
                      disabled={item.status === "expired"}
                      className="rounded-xl border border-ember/15 px-3 py-2 text-xs disabled:opacity-40"
                    >
                      {item.status === "active" ? "Deaktivieren" : "Aktivieren"}
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRevoke(item.id);
                      }}
                      className="rounded-xl border border-ember/15 px-3 py-2 text-xs"
                    >
                      Widerrufen
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!isLoading && items?.length === 0 ? (
        <div className="px-4 py-8 text-sm text-ember/65">
          Keine Promo-Codes für diesen Filter gefunden.
        </div>
      ) : null}
      {isLoading ? <div className="px-4 py-8 text-sm">Daten werden geladen...</div> : null}
    </section>
  );
}
