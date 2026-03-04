"use client";

import { FormEvent, useEffect, useState } from "react";
import { Inter } from "next/font/google";

import { api } from "@/lib/api";
import { ContactWizardModal } from "./_components/contact-wizards";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const TELEGRAM_BOT_URL =
  process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL || "https://t.me/Deine_Deutsch_Quiz_bot";
const TELEGRAM_CHANNEL_URL =
  process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_URL || "https://t.me/doechkurse";
const NOTIZBUCH_APK_URL = process.env.NEXT_PUBLIC_NOTIZBUCH_APK_URL || "#";

const GLASS_CARD_CLASS =
  "rounded-2xl border border-white/40 bg-white/60 shadow-[0_4px_24px_rgba(0,0,0,0.06)] backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_8px_32px_rgba(0,0,0,0.10)]";

const INPUT_CLASS =
  "w-full rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200";

const WISSEN_ARTICLES = [
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
  {
    slug: "artikel-der-die-das",
    title: "Artikel im Deutschen: der/die/das",
  },
  {
    slug: "te-ka-mo-lo-einfach-erklaert",
    title: "TEKAMOLO einfach erklärt",
  },
] as const;

const STAR_POSITIONS = [
  { top: "10%", left: "14%" },
  { top: "18%", left: "76%" },
  { top: "30%", left: "8%" },
  { top: "35%", left: "85%" },
  { top: "58%", left: "18%" },
  { top: "64%", left: "78%" },
  { top: "78%", left: "50%" },
] as const;

type StatsPayload = {
  users: number;
  quizzes: number;
};

type StatsState = {
  users: number | null;
  quizzes: number | null;
  isUnavailable: boolean;
};

type FormStatus = "idle" | "loading" | "success" | "error";

type LoginPayload = {
  requires_2fa: boolean;
};

function formatStatValue(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return value.toLocaleString("de-DE");
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

export default function PublicHomePage() {
  const [stats, setStats] = useState<StatsState>({
    users: null,
    quizzes: null,
    isUnavailable: false,
  });
  const [activeWizard, setActiveWizard] = useState<"student" | "partner" | null>(null);

  const [isLoginOpen, setIsLoginOpen] = useState(false);
  const [loginValue, setLoginValue] = useState("");
  const [passwordValue, setPasswordValue] = useState("");
  const [loginStatus, setLoginStatus] = useState<FormStatus>("idle");
  const [loginFeedback, setLoginFeedback] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadStats() {
      try {
        const response = await api.get<StatsPayload>("/api/stats");
        if (!active) {
          return;
        }
        const users = toFiniteNumber(response.data?.users);
        const quizzes = toFiniteNumber(response.data?.quizzes);
        setStats({
          users,
          quizzes,
          isUnavailable: users === null || quizzes === null,
        });
      } catch {
        if (!active) {
          return;
        }
        setStats({ users: null, quizzes: null, isUnavailable: true });
      }
    }

    void loadStats();

    return () => {
      active = false;
    };
  }, []);

  async function handleAdminLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loginStatus === "loading") {
      return;
    }

    const login = loginValue.trim();
    const password = passwordValue;

    if (!login || !password) {
      setLoginStatus("error");
      setLoginFeedback("Bitte Login und Passwort eingeben.");
      return;
    }

    setLoginStatus("loading");
    setLoginFeedback(null);

    try {
      const response = await api.post<LoginPayload>("/admin/auth/login", {
        email: login,
        password,
      });
      if (response.data.requires_2fa) {
        window.location.href = "/admin/login";
        return;
      }
      window.location.href = "/admin";
    } catch {
      setLoginStatus("error");
      setLoginFeedback("Login fehlgeschlagen. Bitte prüfe deine Daten.");
    } finally {
      setLoginStatus("idle");
    }
  }

  return (
    <main
      lang="de"
      className={`${inter.className} min-h-screen bg-[linear-gradient(135deg,#e8f4f8_0%,#f0f7ee_50%,#fef9f0_100%)] text-slate-800`}
    >
      <header className="sticky top-0 z-40 border-b border-white/50 bg-white/65 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <a href="/" className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[linear-gradient(140deg,#37AEE2,#1A89C9)] text-xs font-bold text-white">
              QA
            </span>
            <span className="text-sm font-bold sm:text-base">Quiz Arena Deutsch</span>
          </a>
          <button
            type="button"
            className="rounded-full p-2 text-slate-700 transition hover:bg-white/70"
            aria-label="Admin Login öffnen"
            onClick={() => {
              setLoginFeedback(null);
              setLoginStatus("idle");
              setIsLoginOpen(true);
            }}
          >
            <LockIcon />
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 pb-16 pt-10 sm:px-6">
        <section
          className={`${GLASS_CARD_CLASS} relative overflow-hidden bg-[linear-gradient(135deg,#dff2fa_0%,#e8f6eb_50%,#fdf5e8_100%)] px-6 py-16 text-center`}
        >
          {STAR_POSITIONS.map((star, index) => (
            <span
              key={`${star.top}-${star.left}`}
              className="pointer-events-none absolute text-lg text-sky-500/80"
              style={{
                top: star.top,
                left: star.left,
                animation: `twinkle 2.8s ease-in-out ${index * 0.2}s infinite`,
              }}
            >
              ✦
            </span>
          ))}
          <h1 className="relative z-10 mx-auto max-w-3xl text-3xl font-semibold leading-tight sm:text-5xl">
            Jeden Tag ein bisschen Deutsch.
          </h1>
        </section>

        <section className="mt-8">
          <div className={`${GLASS_CARD_CLASS} flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between`}>
            <div className="flex items-start gap-4">
              <TelegramIcon />
              <div>
                <h3 className="text-xl font-semibold">Telegram-Kanal</h3>
                <p className="mt-1 text-sm text-slate-600">
                  Tipps, Übungen und News zum Deutschlernen.
                </p>
              </div>
            </div>
            <a
              href={TELEGRAM_CHANNEL_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white/80 px-5 py-2 text-sm font-medium text-slate-800 transition hover:bg-white"
            >
              Kanal öffnen
            </a>
          </div>
        </section>

        <section className="mt-6">
          <div className={`${GLASS_CARD_CLASS} grid gap-6 p-6 lg:grid-cols-5`}>
            <div className="lg:col-span-3">
              <div className="flex items-start gap-4">
                <BotIcon />
                <div>
                  <h3 className="text-2xl font-semibold">Quiz Arena Bot</h3>
                  <ul className="mt-4 space-y-2 text-sm text-slate-700">
                    <li className="flex gap-2">
                      <span className="text-emerald-600">✓</span>
                      <span>Dein persönlicher Deutschlern-Bot</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-emerald-600">✓</span>
                      <span>Tägliche Quizze und spielerische Übungen</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-emerald-600">✓</span>
                      <span>Verfolge deinen Fortschritt jeden Tag</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-emerald-600">✓</span>
                      <span>Streaks und Wettkämpfe mit Freunden</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-emerald-600">✓</span>
                      <span>Wortschatz und Grammatik trainieren</span>
                    </li>
                  </ul>
                </div>
              </div>
              <a
                href={TELEGRAM_BOT_URL}
                target="_blank"
                rel="noreferrer"
                className="mt-6 inline-flex rounded-full bg-[#E8734A] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#db6740]"
              >
                Bot öffnen
              </a>
            </div>

            <div className="lg:col-span-2">
              <div className="grid grid-cols-2 gap-3">
                <article className="rounded-xl border border-white/50 bg-white/75 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Users</p>
                  <p className="mt-2 text-2xl font-semibold">{formatStatValue(stats.users)}</p>
                  {stats.isUnavailable ? (
                    <p className="mt-1 text-xs text-slate-500">temporarily unavailable</p>
                  ) : null}
                </article>
                <article className="rounded-xl border border-white/50 bg-white/75 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Quizzes played</p>
                  <p className="mt-2 text-2xl font-semibold">{formatStatValue(stats.quizzes)}</p>
                  {stats.isUnavailable ? (
                    <p className="mt-1 text-xs text-slate-500">temporarily unavailable</p>
                  ) : null}
                </article>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-10">
          <h2 className="text-3xl font-semibold">Produkte</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <article className={`${GLASS_CARD_CLASS} flex h-full flex-col p-5`}>
              <div className="text-3xl">📓</div>
              <h4 className="mt-2 text-xl font-semibold">Notizbuch</h4>
              <p className="mt-1 text-sm text-slate-600">Leicht · Offline · 10 MB</p>
              <a
                href={NOTIZBUCH_APK_URL}
                className="mt-auto inline-flex rounded-full border border-slate-300 bg-white/80 px-4 py-2 text-sm font-medium"
              >
                Download / Android APK
              </a>
            </article>

            <article className={`${GLASS_CARD_CLASS} flex h-full flex-col p-5`}>
              <div className="text-3xl">🔜</div>
              <h4 className="mt-2 text-xl font-semibold">Coming soon</h4>
              <p className="mt-1 text-sm text-slate-600">Neues Tool in Arbeit</p>
              <button
                type="button"
                disabled
                className="mt-auto cursor-not-allowed rounded-full border border-slate-200 bg-slate-100 px-4 py-2 text-sm text-slate-500"
              >
                Bald verfügbar
              </button>
            </article>

            <article className={`${GLASS_CARD_CLASS} flex h-full flex-col p-5`}>
              <div className="text-3xl">✨</div>
              <h4 className="mt-2 text-xl font-semibold">Coming soon</h4>
              <p className="mt-1 text-sm text-slate-600">Weitere Projekte geplant</p>
              <button
                type="button"
                disabled
                className="mt-auto cursor-not-allowed rounded-full border border-slate-200 bg-slate-100 px-4 py-2 text-sm text-slate-500"
              >
                Bald verfügbar
              </button>
            </article>
          </div>
        </section>

        <section className="mt-10 grid gap-4 lg:grid-cols-2">
          <article className={`${GLASS_CARD_CLASS} p-6`}>
            <p className="text-2xl">📚</p>
            <h3 className="mt-2 text-2xl font-semibold">Zum Unterricht anmelden</h3>
            <p className="mt-2 text-sm text-slate-600">
              Melde dich für unseren Deutschunterricht an. Wir stellen dir ein kurzes Formular mit
              persönlicher Empfehlung zusammen.
            </p>
            <ul className="mt-4 space-y-2 text-sm text-slate-700">
              <li>• 3 Schritte: Profil, Lernformat, Kontakt</li>
              <li>• Nur notwendige Fragen, klare Optionen</li>
              <li>• Rückmeldung innerhalb von 24 Stunden</li>
            </ul>
            <button
              type="button"
              onClick={() => {
                setIsLoginOpen(false);
                setActiveWizard("student");
              }}
              className="mt-6 rounded-full bg-slate-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
            >
              Anfrage senden
            </button>
          </article>

          <article className={`${GLASS_CARD_CLASS} p-6`}>
            <p className="text-2xl">🤝</p>
            <h3 className="mt-2 text-2xl font-semibold">Kooperation / Partnerschaft</h3>
            <p className="mt-2 text-sm text-slate-600">Kooperiere mit uns für gemeinsame Projekte.</p>
            <ul className="mt-4 space-y-2 text-sm text-slate-700">
              <li>• 2 Schritte für schnelle B2B-Anfrage</li>
              <li>• Fokus auf Angebot, Erwartung und Timing</li>
              <li>• Antwort in 2-3 Werktagen</li>
            </ul>
            <button
              type="button"
              onClick={() => {
                setIsLoginOpen(false);
                setActiveWizard("partner");
              }}
              className="mt-6 rounded-full bg-slate-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
            >
              Kontakt aufnehmen
            </button>
          </article>
        </section>

        <section className="mt-10">
          <h2 className="text-3xl font-semibold">Wissen & Tipps</h2>
          <div className="mt-4 space-y-3">
            {WISSEN_ARTICLES.map((article) => (
              <a
                key={article.slug}
                href={`/artikel/${article.slug}`}
                className={`${GLASS_CARD_CLASS} flex items-center justify-between px-5 py-4 text-sm sm:text-base`}
              >
                <span>{article.title}</span>
                <span className="text-xl text-slate-500">›</span>
              </a>
            ))}
          </div>
        </section>

        <footer className="mt-12 border-t border-white/60 pt-6 text-center text-sm text-slate-600">
          <p>
            <a href={TELEGRAM_CHANNEL_URL} target="_blank" rel="noreferrer" className="hover:underline">
              Telegram-Kanal
            </a>{" "}
            ·{" "}
            <a href={TELEGRAM_BOT_URL} target="_blank" rel="noreferrer" className="hover:underline">
              Quiz Arena Bot
            </a>
          </p>
          <p className="mt-2">© 2025 Quiz Arena Deutsch · contact@deutchquizarena.de</p>
        </footer>
      </div>

      <ContactWizardModal
        kind="student"
        isOpen={activeWizard === "student"}
        onClose={() => setActiveWizard(null)}
      />
      <ContactWizardModal
        kind="partner"
        isOpen={activeWizard === "partner"}
        onClose={() => setActiveWizard(null)}
      />

      {isLoginOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-white/30 p-4 backdrop-blur-sm"
          onClick={() => setIsLoginOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-white/50 bg-white/85 p-5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-2xl font-semibold">Admin Login</h3>
              <button
                type="button"
                className="rounded-full px-2 py-1 text-lg leading-none text-slate-600 transition hover:bg-slate-100"
                onClick={() => setIsLoginOpen(false)}
                aria-label="Schließen"
              >
                ✕
              </button>
            </div>

            <form className="mt-4 space-y-3" onSubmit={handleAdminLogin}>
              <input
                type="text"
                className={INPUT_CLASS}
                placeholder="Login"
                value={loginValue}
                onChange={(event) => setLoginValue(event.target.value)}
                autoComplete="username"
              />
              <input
                type="password"
                className={INPUT_CLASS}
                placeholder="Password"
                value={passwordValue}
                onChange={(event) => setPasswordValue(event.target.value)}
                autoComplete="current-password"
              />
              <button
                type="submit"
                disabled={loginStatus === "loading"}
                className="w-full rounded-full bg-slate-800 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {loginStatus === "loading" ? "Einloggen..." : "Einloggen"}
              </button>
            </form>

            {loginFeedback ? <p className="mt-3 text-sm text-red-600">{loginFeedback}</p> : null}
          </div>
        </div>
      ) : null}

      <style jsx global>{`
        @keyframes twinkle {
          0%,
          100% {
            opacity: 0.35;
            transform: scale(0.9);
          }
          50% {
            opacity: 1;
            transform: scale(1.15);
          }
        }
      `}</style>
    </main>
  );
}

function LockIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M8.5 10V7.5a3.5 3.5 0 1 1 7 0V10"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function TelegramIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
      <circle cx="20" cy="20" r="20" fill="#27A6E5" />
      <path
        d="M9 19.6L30.2 11.4c1-.4 1.8.2 1.5 1.6l-3.6 16.9c-.2 1-1 1.3-1.8.8l-5.4-4-2.6 2.5c-.3.3-.5.5-1 .5l.4-5.5L27.8 15c.4-.4-.1-.7-.6-.3l-12.4 7.8-5.3-1.6c-1.1-.4-1.1-1.1.2-1.3z"
        fill="#fff"
      />
    </svg>
  );
}

function BotIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
      <rect x="8" y="10" width="24" height="22" rx="8" fill="#26A69A" />
      <rect x="17" y="5" width="6" height="7" rx="3" fill="#26A69A" />
      <circle cx="16" cy="20" r="2.2" fill="#fff" />
      <circle cx="24" cy="20" r="2.2" fill="#fff" />
      <rect x="14" y="25" width="12" height="2.5" rx="1.25" fill="#fff" />
    </svg>
  );
}
