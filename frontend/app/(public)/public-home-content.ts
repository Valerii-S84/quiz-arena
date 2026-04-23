export const BOT_LOGO_PATH = "/logo/bot-logo.jpg";
export const CHANNEL_LOGO_PATH = "/logo/channel-logo.jpg";
export const WORKLOG_LOGO_PATH = "/products/worklog/logo.png";
export const WORKLOG_DOWNLOAD_PATH = "/downloads/worklog/direct-hoofdrapport.apk";

export const GLASS_CARD_CLASS =
  "rounded-2xl border border-white/70 bg-white/74 shadow-[0_10px_30px_rgba(15,23,42,0.10)] backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_16px_38px_rgba(15,23,42,0.16)]";

export const ORANGE_BUTTON_CLASS =
  "inline-flex items-center justify-center rounded-full bg-[#E8734A] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(232,115,74,0.33)] transition hover:bg-[#d7653f]";

export const INPUT_CLASS =
  "w-full rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200";

export const WISSEN_ARTICLES = [
  {
    slug: "deutsche-sprache-geschichte",
    title: "Geschichte der deutschen Sprache",
  },
  {
    slug: "sprachniveaus-a1-c1",
    title: "Sprachniveaus A1–C1: was bedeutet das?",
  },
  {
    slug: "pruefungen-goethe-telc-testdaf",
    title: "Prüfungen: Goethe / telc / TestDaF",
  },
] as const;

export const STAR_POSITIONS = [
  { top: "10%", left: "14%" },
  { top: "18%", left: "76%" },
  { top: "30%", left: "8%" },
  { top: "35%", left: "85%" },
  { top: "58%", left: "18%" },
  { top: "64%", left: "78%" },
  { top: "78%", left: "50%" },
] as const;
