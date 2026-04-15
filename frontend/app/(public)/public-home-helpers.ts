import type { StatsState } from "./public-home-types";

export function formatStatValue(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return value.toLocaleString("de-DE");
}

export function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

export function buildTrackedTelegramBotUrl(baseUrl: string, startPayload: string): string {
  try {
    const url = new URL(baseUrl);
    url.searchParams.set("start", startPayload);
    return url.toString();
  } catch {
    const separator = baseUrl.includes("?") ? "&" : "?";
    return `${baseUrl}${separator}start=${encodeURIComponent(startPayload)}`;
  }
}

export function createInitialStatsState(): StatsState {
  return {
    users: null,
    quizzes: null,
    isUnavailable: false,
  };
}

export function createUnavailableStatsState(): StatsState {
  return {
    users: null,
    quizzes: null,
    isUnavailable: true,
  };
}

export function normalizePublicStats(payload: {
  users?: unknown;
  quizzes?: unknown;
}): StatsState {
  const users = toFiniteNumber(payload.users);
  const quizzes = toFiniteNumber(payload.quizzes);

  return {
    users,
    quizzes,
    isUnavailable: users === null || quizzes === null,
  };
}
