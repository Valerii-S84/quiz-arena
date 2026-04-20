"use client";

import { type FormEvent, useState } from "react";
import { Inter } from "next/font/google";

import { ContactWizardModal } from "./_components/contact-wizards";
import {
  TELEGRAM_BOT_START_PAYLOAD,
  TELEGRAM_BOT_URL,
} from "./public-home-content";
import {
  requestAdminLogin,
  submitAdminLogin,
  usePublicStats,
} from "./public-home-data";
import { navigateTo } from "@/lib/browser-navigation";
import { buildTrackedTelegramBotUrl } from "./public-home-helpers";
import { PublicHomeAdminLoginModal } from "./public-home-admin-login-modal";
import {
  PublicHomeBotSection,
  PublicHomeChannelSection,
  PublicHomeContactSection,
  PublicHomeFooter,
  PublicHomeHeader,
  PublicHomeHero,
  PublicHomeKnowledgeSection,
  PublicHomeProductsSection,
} from "./public-home-sections";
import type { ActiveWizard, FormStatus } from "./public-home-types";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export default function PublicHomeClient() {
  const stats = usePublicStats();
  const [activeWizard, setActiveWizard] = useState<ActiveWizard>(null);
  const [isLoginOpen, setIsLoginOpen] = useState(false);
  const [loginValue, setLoginValue] = useState("");
  const [passwordValue, setPasswordValue] = useState("");
  const [loginStatus, setLoginStatus] = useState<FormStatus>("idle");
  const [loginFeedback, setLoginFeedback] = useState<string | null>(null);

  const trackedTelegramBotUrl = buildTrackedTelegramBotUrl(
    TELEGRAM_BOT_URL,
    TELEGRAM_BOT_START_PAYLOAD,
  );

  function openAdminLogin() {
    setLoginFeedback(null);
    setLoginStatus("idle");
    setIsLoginOpen(true);
  }

  async function handleAdminLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loginStatus === "loading") {
      return;
    }

    setLoginStatus("loading");
    setLoginFeedback(null);

    const result = await submitAdminLogin(
      {
        login: loginValue,
        password: passwordValue,
      },
      requestAdminLogin,
    );

    if (result.redirectTo) {
      navigateTo(result.redirectTo);
    }

    setLoginStatus(result.status);
    setLoginFeedback(result.feedback);
  }

  return (
    <main
      lang="de"
      className={`${inter.className} min-h-screen bg-[linear-gradient(135deg,#d7ebf5_0%,#e4f1e0_50%,#f8ecd8_100%)] text-slate-900`}
    >
      <PublicHomeHeader onOpenAdminLogin={openAdminLogin} />

      <div className="mx-auto max-w-6xl px-4 pb-16 pt-10 sm:px-6">
        <PublicHomeHero />
        <PublicHomeChannelSection />
        <PublicHomeBotSection trackedTelegramBotUrl={trackedTelegramBotUrl} stats={stats} />
        <PublicHomeProductsSection />
        <PublicHomeContactSection
          onOpenStudentWizard={() => {
            setIsLoginOpen(false);
            setActiveWizard("student");
          }}
          onOpenPartnerWizard={() => {
            setIsLoginOpen(false);
            setActiveWizard("partner");
          }}
        />
        <PublicHomeKnowledgeSection />
        <PublicHomeFooter />
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

      <PublicHomeAdminLoginModal
        isOpen={isLoginOpen}
        loginValue={loginValue}
        passwordValue={passwordValue}
        loginStatus={loginStatus}
        loginFeedback={loginFeedback}
        onClose={() => setIsLoginOpen(false)}
        onLoginChange={setLoginValue}
        onPasswordChange={setPasswordValue}
        onSubmit={handleAdminLogin}
      />

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
