import type { ReactNode } from "react";

type PromoModalFrameProps = {
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  position?: "center" | "top";
};

export function PromoModalFrame({
  children,
  onClose,
  wide = false,
  position = "center",
}: PromoModalFrameProps) {
  return (
    <div
      className={`fixed inset-0 z-40 flex justify-center bg-[#1d160f]/55 p-4 ${
        position === "top" ? "items-start pt-12 sm:pt-16" : "items-center"
      }`}
    >
      <div
        className={`surface max-h-[90vh] w-full overflow-y-auto rounded-[28px] border border-white/60 p-5 shadow-2xl ${
          wide ? "max-w-5xl" : "max-w-3xl"
        }`}
      >
        <div className="mb-4 flex items-center justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-ember/15 px-3 py-1 text-sm"
          >
            Schließen
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
