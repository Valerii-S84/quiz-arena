import Image from "next/image";
import Link from "next/link";

import {
  BOT_LOGO_PATH,
  CHANNEL_LOGO_PATH,
  GLASS_CARD_CLASS,
  ORANGE_BUTTON_CLASS,
  STAR_POSITIONS,
  TELEGRAM_CHANNEL_URL,
  WISSEN_ARTICLES,
  WORKLOG_DOWNLOAD_PATH,
  WORKLOG_LOGO_PATH,
} from "./public-home-content";
import { formatStatValue } from "./public-home-helpers";
import type { StatsState } from "./public-home-types";

type PublicHomeHeaderProps = {
  onOpenAdminLogin: () => void;
};

type PublicHomeBotSectionProps = {
  trackedTelegramBotUrl: string;
  stats: StatsState;
};

type PublicHomeContactSectionProps = {
  onOpenStudentWizard: () => void;
  onOpenPartnerWizard: () => void;
};

export function PublicHomeHeader({ onOpenAdminLogin }: PublicHomeHeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/60 bg-white/82 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-3">
          <span className="relative h-8 w-8 overflow-hidden rounded-full ring-1 ring-white/80 shadow-[0_6px_14px_rgba(15,23,42,0.25)]">
            <Image
              src={BOT_LOGO_PATH}
              alt="Deutsch Quiz Arena Logo"
              fill
              sizes="32px"
              className="object-cover"
            />
          </span>
          <span className="text-sm font-bold sm:text-base">Quiz Arena Deutsch</span>
        </Link>
        <button
          type="button"
          className="rounded-full p-2 text-slate-800 transition hover:bg-white/80"
          aria-label="Admin Login öffnen"
          onClick={onOpenAdminLogin}
        >
          <LockIcon />
        </button>
      </div>
    </header>
  );
}

export function PublicHomeHero() {
  return (
    <section
      className={`${GLASS_CARD_CLASS} relative overflow-hidden bg-[linear-gradient(135deg,#cfe7f3_0%,#dcedd7_50%,#f7e6c8_100%)] px-6 py-16 text-center`}
    >
      {STAR_POSITIONS.map((star, index) => (
        <span
          key={`${star.top}-${star.left}`}
          className="pointer-events-none absolute text-lg text-sky-700/85"
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
  );
}

export function PublicHomeChannelSection() {
  return (
    <section className="mt-8">
      <div
        className={`${GLASS_CARD_CLASS} flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between`}
      >
        <div className="flex items-start gap-4">
          <div className="relative h-10 w-10 shrink-0 overflow-hidden rounded-full ring-1 ring-white/80">
            <Image
              src={CHANNEL_LOGO_PATH}
              alt="Deutsch ist einfach Kanal Logo"
              fill
              sizes="40px"
              className="object-cover"
            />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-sky-800">
              Telegram-Kanal
            </p>
            <h3 className="mt-1 text-xl font-semibold">
              Deutsch ist einfach! · Täglich & Praxis 🇩🇪
            </h3>
            <p className="mt-2 text-sm text-slate-700">
              📚 Deutsch — dein täglicher Begleiter 🇩🇪 Kurze, klare Lernposts: Wortschatz mit
              Artikeln, einfache Grammatik, Dialoge zum Mitmachen.
            </p>
            <p className="mt-1 text-sm text-slate-700">
              Dazu bekommst du Mini-Übungen, alltagstaugliche Redemittel und kompakte Tipps für
              Prüfungen, Arbeit und sichere Kommunikation im echten Leben.
            </p>
          </div>
        </div>
        <a
          href={TELEGRAM_CHANNEL_URL}
          target="_blank"
          rel="noreferrer"
          className={ORANGE_BUTTON_CLASS}
        >
          Kanal öffnen
        </a>
      </div>
    </section>
  );
}

export function PublicHomeBotSection({
  trackedTelegramBotUrl,
  stats,
}: PublicHomeBotSectionProps) {
  return (
    <section className="mt-6">
      <div className={`${GLASS_CARD_CLASS} grid gap-6 p-6 lg:grid-cols-5`}>
        <div className="lg:col-span-3">
          <div className="flex items-start gap-4">
            <div className="relative h-10 w-10 shrink-0 overflow-hidden rounded-full ring-1 ring-white/80">
              <Image
                src={BOT_LOGO_PATH}
                alt="Deutsch Quiz Arena Bot Logo"
                fill
                sizes="40px"
                className="object-cover"
              />
            </div>
            <div>
              <h3 className="text-2xl font-semibold">Deutsch Quiz Arena</h3>
              <p className="mt-2 text-sm text-slate-700">
                Interaktives Lernen mit klaren Lernpfaden, täglicher Motivation und messbarem
                Fortschritt.
              </p>
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
            href={trackedTelegramBotUrl}
            target="_blank"
            rel="noreferrer"
            className={`mt-6 ${ORANGE_BUTTON_CLASS}`}
          >
            Bot öffnen
          </a>
        </div>

        <div className="lg:col-span-2">
          <div className="grid grid-cols-1 gap-3">
            <article className="rounded-xl border border-white/60 bg-white/82 p-4 shadow-[0_8px_20px_rgba(15,23,42,0.08)]">
              <p className="text-xs uppercase tracking-wide text-slate-600">Nutzer</p>
              <p className="mt-2 text-2xl font-semibold">{formatStatValue(stats.users)}</p>
              {stats.isUnavailable ? (
                <p className="mt-1 text-xs text-slate-500">vorübergehend nicht verfügbar</p>
              ) : null}
            </article>
            <article className="rounded-xl border border-white/60 bg-white/82 p-4 shadow-[0_8px_20px_rgba(15,23,42,0.08)]">
              <p className="text-xs uppercase tracking-wide text-slate-600">Gespielte Quizze</p>
              <p className="mt-2 text-2xl font-semibold">{formatStatValue(stats.quizzes)}</p>
              {stats.isUnavailable ? (
                <p className="mt-1 text-xs text-slate-500">vorübergehend nicht verfügbar</p>
              ) : null}
            </article>
          </div>
        </div>
      </div>
    </section>
  );
}

export function PublicHomeProductsSection() {
  return (
    <section className="mt-10">
      <h2 className="text-3xl font-semibold text-slate-900">Produkte</h2>
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-start">
        <article className={`${GLASS_CARD_CLASS} p-5 sm:p-6`}>
          <div className="flex items-start gap-4">
            <div className="relative h-10 w-10 shrink-0 overflow-hidden rounded-full ring-1 ring-white/80">
              <Image
                src={WORKLOG_LOGO_PATH}
                alt="Worklog Logo"
                fill
                sizes="40px"
                className="object-cover"
              />
            </div>
            <div className="flex flex-1 flex-col">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Android App
              </p>
              <h4 className="mt-1 text-xl font-semibold text-slate-900">Worklog</h4>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                Sprach-Notizblock für Android: Sprache wählen, sprechen und Einträge lokal mit
                Datum speichern. Schnell, klar und ohne Cloud-Zwang.
              </p>
              <ul className="mt-3 space-y-1.5 text-sm text-slate-700">
                <li className="flex gap-2">
                  <span className="text-emerald-600">✓</span>
                  <span>Mehrsprachige Spracheingabe</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-emerald-600">✓</span>
                  <span>Lokaler Verlauf mit Zeitstempel</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-emerald-600">✓</span>
                  <span>Einträge ansehen und löschen</span>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-3 border-t border-white/60 pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-slate-600">
              Direkter Download als Android-App (.apk), ca. 9 MB.
            </p>
            <a
              href={WORKLOG_DOWNLOAD_PATH}
              download="worklog-direct-hoofdrapport.apk"
              className="inline-flex items-center justify-center rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-[0_8px_18px_rgba(15,23,42,0.22)] transition hover:bg-slate-800"
            >
              APK herunterladen
            </a>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Android: Datei öffnen, Installation erlauben, App starten.
          </p>
        </article>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
          <article className={`${GLASS_CARD_CLASS} flex h-full flex-col p-5`}>
            <div className="text-3xl">🔜</div>
            <h4 className="mt-2 text-xl font-semibold">Bald verfügbar</h4>
            <p className="mt-1 text-sm text-slate-700">Neues Tool in Arbeit</p>
            <button
              type="button"
              disabled
              className="mt-auto cursor-not-allowed rounded-full border border-slate-300 bg-slate-200 px-4 py-2 text-sm text-slate-600"
            >
              Bald verfügbar
            </button>
          </article>

          <article className={`${GLASS_CARD_CLASS} flex h-full flex-col p-5`}>
            <div className="text-3xl">✨</div>
            <h4 className="mt-2 text-xl font-semibold">Bald verfügbar</h4>
            <p className="mt-1 text-sm text-slate-700">Weitere Projekte geplant</p>
            <button
              type="button"
              disabled
              className="mt-auto cursor-not-allowed rounded-full border border-slate-300 bg-slate-200 px-4 py-2 text-sm text-slate-600"
            >
              Bald verfügbar
            </button>
          </article>
        </div>
      </div>
    </section>
  );
}

export function PublicHomeContactSection({
  onOpenStudentWizard,
  onOpenPartnerWizard,
}: PublicHomeContactSectionProps) {
  return (
    <section className="mt-10 grid gap-4 lg:grid-cols-2">
      <article className={`${GLASS_CARD_CLASS} p-6`}>
        <p className="text-2xl">📚</p>
        <h3 className="mt-2 text-2xl font-semibold">Zum Unterricht anmelden</h3>
        <p className="mt-2 text-sm text-slate-700">
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
          onClick={onOpenStudentWizard}
          className={`mt-6 ${ORANGE_BUTTON_CLASS}`}
        >
          Anfrage senden
        </button>
      </article>

      <article className={`${GLASS_CARD_CLASS} p-6`}>
        <p className="text-2xl">🤝</p>
        <h3 className="mt-2 text-2xl font-semibold">Kooperation / Partnerschaft</h3>
        <p className="mt-2 text-sm text-slate-700">Kooperiere mit uns für gemeinsame Projekte.</p>
        <ul className="mt-4 space-y-2 text-sm text-slate-700">
          <li>• 2 Schritte für schnelle B2B-Anfrage</li>
          <li>• Fokus auf Angebot, Erwartung und Timing</li>
          <li>• Antwort in 2-3 Werktagen</li>
        </ul>
        <button
          type="button"
          onClick={onOpenPartnerWizard}
          className="mt-6 inline-flex items-center justify-center rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(15,23,42,0.28)] transition hover:bg-slate-800"
        >
          Kontakt aufnehmen
        </button>
      </article>
    </section>
  );
}

export function PublicHomeKnowledgeSection() {
  return (
    <section className="mt-10">
      <h2 className="text-3xl font-semibold">Wissen & Tipps</h2>
      <div className="mt-4 space-y-3">
        {WISSEN_ARTICLES.map((article) => (
          <Link
            key={article.slug}
            href={`/artikel/${article.slug}`}
            className={`${GLASS_CARD_CLASS} flex items-center justify-between px-5 py-4 text-sm transition hover:border-sky-200 sm:text-base`}
          >
            <span>{article.title}</span>
            <span className="text-xl text-slate-700">›</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

export function PublicHomeFooter() {
  return (
    <footer className="mt-12 border-t border-white/70 pt-6 text-center text-sm text-slate-700">
      <p>© 2025 Chik&amp;com</p>
    </footer>
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
