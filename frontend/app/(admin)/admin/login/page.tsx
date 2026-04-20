"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { api } from "@/lib/api";
import { navigateTo } from "@/lib/browser-navigation";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

type LoginForm = z.infer<typeof loginSchema>;
type LoginResponse = {
  requires_2fa: boolean;
};

export default function AdminLoginPage() {
  const [requires2FA, setRequires2FA] = useState(false);
  const [totpCode, setTotpCode] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const form = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function onSubmit(values: LoginForm) {
    setErrorMessage(null);
    try {
      const response = await api.post<LoginResponse>("/admin/auth/login", values);
      if (response.data.requires_2fa) {
        setRequires2FA(true);
        return;
      }
      navigateTo("/admin/dashboard");
    } catch (error) {
      setErrorMessage("Не вдалося увійти. Перевір email/password.");
      setRequires2FA(false);
    }
  }

  async function verify2FA() {
    setErrorMessage(null);
    try {
      await api.post("/admin/auth/2fa/verify", { code: totpCode });
      navigateTo("/admin/dashboard");
    } catch {
      setErrorMessage("Невірний 2FA код.");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <div className="surface rounded-2xl p-6">
        <h1 className="text-3xl">Admin Login</h1>
        {!requires2FA ? (
          <form className="mt-5 space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
            <input
              type="email"
              className="w-full rounded-xl border border-ember/20 bg-white px-3 py-2"
              placeholder="Email"
              {...form.register("email")}
            />
            <input
              type="password"
              className="w-full rounded-xl border border-ember/20 bg-white px-3 py-2"
              placeholder="Password"
              {...form.register("password")}
            />
            <button type="submit" className="w-full rounded-xl bg-ember px-3 py-2 text-sand">
              Sign In
            </button>
          </form>
        ) : (
          <div className="mt-5 space-y-3">
            <input
              value={totpCode}
              onChange={(event) => setTotpCode(event.target.value)}
              className="w-full rounded-xl border border-ember/20 bg-white px-3 py-2"
              placeholder="2FA Code"
            />
            <button className="w-full rounded-xl bg-coral px-3 py-2" onClick={verify2FA}>
              Verify 2FA
            </button>
          </div>
        )}
        {errorMessage ? <p className="mt-4 text-sm text-red-700">{errorMessage}</p> : null}
      </div>
    </main>
  );
}
