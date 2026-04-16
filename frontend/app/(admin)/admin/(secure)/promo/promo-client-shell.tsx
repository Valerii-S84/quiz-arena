import { PromoCodeModal } from "./promo-code-modal";
import { PromoDetailPanel } from "./promo-detail-panel";
import { PromoFormModal } from "./promo-form-modal";
import { PromoListTable } from "./promo-list-table";
import { usePromoClientState } from "./use-promo-client-state";
import type { PromoStatusFilter } from "./promo-types";

const STATUS_FILTER_TABS: Array<{ id: PromoStatusFilter; label: string }> = [
  { id: "all", label: "Alle" },
  { id: "active", label: "Aktiv" },
  { id: "inactive", label: "Inaktiv" },
  { id: "expired", label: "Abgelaufen" },
];

export function PromoClientShell() {
  const promoState = usePromoClientState();

  return (
    <main className="space-y-6 py-2 fade-in">
      <header className="surface overflow-hidden rounded-[32px] border border-white/60 p-6">
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <p className="text-xs uppercase tracking-[0.26em] text-ember/55">Promo-Werkbank</p>
            <h1 className="mt-3 text-4xl">Codes erzeugen, prüfen und sauber nachverfolgen</h1>
            <p className="mt-3 max-w-2xl text-sm text-ember/75">
              Suche, Statuswechsel, One-time-Code-Ausgabe, Statistik und Audit liegen jetzt in
              einem Operator-Flow.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => promoState.setCreateOpen(true)}
              className="rounded-[24px] bg-ember px-5 py-4 text-left text-sand shadow-lg"
            >
              <p className="text-xs uppercase tracking-[0.2em] text-sand/70">Aktion</p>
              <p className="mt-2 text-xl">Promo-Code erstellen</p>
            </button>
            <button
              type="button"
              onClick={() => promoState.setBulkOpen(true)}
              className="rounded-[24px] border border-ember/15 bg-white/80 px-5 py-4 text-left"
            >
              <p className="text-xs uppercase tracking-[0.2em] text-ember/55">Aktion</p>
              <p className="mt-2 text-xl">Massen-Generierung</p>
            </button>
          </div>
        </div>
      </header>

      <section className="surface rounded-[28px] p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {STATUS_FILTER_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => promoState.setStatusFilter(tab.id)}
                className={`rounded-full px-4 py-2 text-sm ${
                  promoState.statusFilter === tab.id
                    ? "bg-ember text-sand"
                    : "border border-ember/15 bg-white"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <input
            value={promoState.searchInput}
            onChange={(event) => promoState.setSearchInput(event.target.value)}
            placeholder="Nach Code-Präfix oder Kampagne suchen"
            className="w-full rounded-2xl border border-ember/15 bg-white px-4 py-3 text-sm lg:max-w-md"
          />
        </div>
      </section>

      {promoState.flash ? (
        <div
          className={`rounded-2xl border px-4 py-3 text-sm ${
            promoState.flash.kind === "error"
              ? "border-red-200 bg-red-50 text-red-700"
              : "border-emerald-200 bg-emerald-50 text-emerald-700"
          }`}
        >
          {promoState.flash.text}
        </div>
      ) : null}

      <PromoListTable
        items={promoState.promoQuery.data?.items}
        products={promoState.productsQuery.data?.items}
        isLoading={promoState.promoQuery.isLoading}
        onOpenDetails={promoState.openDetailWithParams}
        onOpenStats={promoState.openDetailWithStats}
        onEdit={promoState.openEditModal}
        onToggle={(promoId) => {
          void promoState.toggleMutation.mutateAsync(promoId);
        }}
        onRevoke={(promoId) => {
          void promoState.handleRevoke(promoId);
        }}
      />

      {promoState.createOpen ? (
        <PromoFormModal
          title="Promo-Code erstellen"
          values={promoState.createForm}
          setValues={promoState.setCreateForm}
          products={promoState.productsQuery.data?.items}
          submitLabel="Promo-Code speichern"
          onClose={() => promoState.setCreateOpen(false)}
          onSubmit={async () => {
            await promoState.createMutation.mutateAsync();
          }}
          isPending={promoState.createMutation.isPending}
          mode="create"
        />
      ) : null}

      {promoState.bulkOpen ? (
        <PromoFormModal
          title="Massen-Generierung"
          values={promoState.bulkForm}
          setValues={promoState.setBulkForm}
          products={promoState.productsQuery.data?.items}
          submitLabel="Codes erzeugen"
          onClose={() => promoState.setBulkOpen(false)}
          onSubmit={async () => {
            await promoState.bulkMutation.mutateAsync();
          }}
          isPending={promoState.bulkMutation.isPending}
          mode="bulk"
        />
      ) : null}

      {promoState.editPromo ? (
        <PromoFormModal
          title="Promo-Code bearbeiten"
          values={promoState.editForm}
          setValues={promoState.setEditForm}
          products={promoState.productsQuery.data?.items}
          submitLabel="Änderungen speichern"
          onClose={() => promoState.setEditPromo(null)}
          onSubmit={async () => {
            await promoState.updateMutation.mutateAsync();
          }}
          isPending={promoState.updateMutation.isPending}
          mode="edit"
        />
      ) : null}

      {promoState.codeModal ? (
        <PromoCodeModal
          state={promoState.codeModal}
          onClose={promoState.closeCodeModal}
          onCopyAll={promoState.handleCopyAll}
        />
      ) : null}

      {promoState.detailId !== null ? (
        <PromoDetailPanel
          promoId={promoState.detailId}
          detailTab={promoState.detailTab}
          detail={promoState.detailQuery.data}
          stats={promoState.statsQuery.data}
          audit={promoState.auditQuery.data}
          products={promoState.productsQuery.data?.items}
          session={promoState.sessionQuery.data}
          revealedCode={promoState.revealedCode}
          onClose={() => promoState.setDetailId(null)}
          onChangeTab={promoState.setDetailTab}
          onRevealCode={(promoId) => {
            void promoState.revealMutation.mutateAsync(promoId);
          }}
          onCopyRevealedCode={(value) => {
            void navigator.clipboard.writeText(value);
          }}
          onEdit={promoState.openEditModal}
          onToggle={(promoId) => {
            void promoState.toggleMutation.mutateAsync(promoId);
          }}
          onRevoke={(promoId) => {
            void promoState.handleRevoke(promoId);
          }}
        />
      ) : null}
    </main>
  );
}
