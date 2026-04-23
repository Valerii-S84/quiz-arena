"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { apiRoutes } from "@/lib/api-routes";

import {
  createInitialStatsState,
  createUnavailableStatsState,
  normalizePublicStats,
} from "./public-home-helpers";
import type {
  AdminLoginCredentials,
  AdminLoginRequest,
  AdminLoginResult,
  LoginPayload,
  StatsPayload,
  StatsState,
} from "./public-home-types";

export async function requestPublicStats(): Promise<StatsPayload> {
  const response = await api.get<StatsPayload>(apiRoutes.public.stats);
  return response.data;
}

export async function loadPublicStats(
  loadStats: () => Promise<{ users?: unknown; quizzes?: unknown }>,
): Promise<StatsState> {
  try {
    const payload = await loadStats();
    return normalizePublicStats(payload);
  } catch {
    return createUnavailableStatsState();
  }
}

export function usePublicStats() {
  const [stats, setStats] = useState<StatsState>(createInitialStatsState());

  useEffect(() => {
    let active = true;

    async function fetchStats() {
      const nextState = await loadPublicStats(requestPublicStats);
      if (!active) {
        return;
      }
      setStats(nextState);
    }

    void fetchStats();

    return () => {
      active = false;
    };
  }, []);

  return stats;
}

export async function requestAdminLogin(payload: AdminLoginRequest): Promise<LoginPayload> {
  const response = await api.post<LoginPayload>(apiRoutes.admin.auth.login, payload);
  return response.data;
}

export async function submitAdminLogin(
  credentials: AdminLoginCredentials,
  loginRequest: (payload: AdminLoginRequest) => Promise<LoginPayload>,
): Promise<AdminLoginResult> {
  const login = credentials.login.trim();
  const password = credentials.password;

  if (!login || !password) {
    return {
      status: "error",
      feedback: "Bitte Login und Passwort eingeben.",
      redirectTo: null,
    };
  }

  try {
    const payload = await loginRequest({ email: login, password });
    return {
      status: "idle",
      feedback: null,
      redirectTo: payload.requires_2fa ? "/admin/login" : "/admin",
    };
  } catch {
    return {
      status: "error",
      feedback: "Login fehlgeschlagen. Bitte prüfe deine Daten.",
      redirectTo: null,
    };
  }
}
