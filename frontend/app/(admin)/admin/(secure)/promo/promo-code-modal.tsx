import { downloadPromoCodesCsv } from "./promo-code-export";
import { PromoModalFrame } from "./promo-modal-frame";
import type { CodeModalState } from "./promo-types";

type PromoCodeModalProps = {
  state: CodeModalState;
  onClose: () => void;
  onCopyAll: () => Promise<void>;
};

export function PromoCodeModal({ state, onClose, onCopyAll }: PromoCodeModalProps) {
  return (
    <PromoModalFrame onClose={onClose} wide={state.codes.length > 1}>
      <header>
        <p className="text-xs uppercase tracking-[0.26em] text-red-700">Nur einmal sichtbar</p>
        <h2 className="mt-3 text-3xl">{state.title}</h2>
        <p className="mt-2 text-sm text-ember/70">
          Nach dem Schließen kann der vollständige Code nur noch von `super_admin` erneut angezeigt
          werden.
        </p>
      </header>

      {state.codes.length === 1 ? (
        <div className="mt-6 rounded-[24px] border border-amber-300/60 bg-amber-50 p-5">
          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-2xl bg-white px-4 py-3 font-mono text-xl tracking-[0.24em]">
              {state.codes[0]}
            </div>
            <button
              type="button"
              onClick={() => void onCopyAll()}
              className="rounded-xl border border-ember/15 px-4 py-3 text-sm"
            >
              Kopieren
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void onCopyAll()}
              className="rounded-xl bg-ember px-4 py-2 text-sm text-sand"
            >
              Alle kopieren
            </button>
            <button
              type="button"
              onClick={() => downloadPromoCodesCsv(state.csvRows)}
              className="rounded-xl border border-ember/15 px-4 py-2 text-sm"
            >
              CSV herunterladen
            </button>
          </div>
          <div className="overflow-x-auto rounded-2xl border border-ember/10 bg-white/70">
            <table className="min-w-full text-sm">
              <thead className="border-b border-ember/10 bg-[#f8efe1] text-left">
                <tr>
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Kampagne</th>
                </tr>
              </thead>
              <tbody>
                {state.codes.map((code) => (
                  <tr key={code} className="border-b border-ember/10 last:border-b-0">
                    <td className="px-4 py-3 font-mono">{code}</td>
                    <td className="px-4 py-3">{state.campaignName || "Ohne Namen"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="mt-6 flex justify-end">
        <button
          type="button"
          onClick={onClose}
          className="rounded-2xl bg-ember px-4 py-3 text-sm text-sand"
        >
          Ich habe den Code gesichert
        </button>
      </div>
    </PromoModalFrame>
  );
}
