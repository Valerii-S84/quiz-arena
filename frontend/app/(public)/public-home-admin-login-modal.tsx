import type { FormEvent } from "react";

import { INPUT_CLASS } from "./public-home-content";
import type { FormStatus } from "./public-home-types";

type PublicHomeAdminLoginModalProps = {
  isOpen: boolean;
  loginValue: string;
  passwordValue: string;
  loginStatus: FormStatus;
  loginFeedback: string | null;
  onClose: () => void;
  onLoginChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function PublicHomeAdminLoginModal({
  isOpen,
  loginValue,
  passwordValue,
  loginStatus,
  loginFeedback,
  onClose,
  onLoginChange,
  onPasswordChange,
  onSubmit,
}: PublicHomeAdminLoginModalProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-white/30 p-4 backdrop-blur-sm"
      onClick={onClose}
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
            onClick={onClose}
            aria-label="Schließen"
          >
            ✕
          </button>
        </div>

        <form className="mt-4 space-y-3" onSubmit={onSubmit}>
          <input
            type="text"
            className={INPUT_CLASS}
            placeholder="Login"
            value={loginValue}
            onChange={(event) => onLoginChange(event.target.value)}
            autoComplete="username"
          />
          <input
            type="password"
            className={INPUT_CLASS}
            placeholder="Passwort"
            value={passwordValue}
            onChange={(event) => onPasswordChange(event.target.value)}
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
  );
}
