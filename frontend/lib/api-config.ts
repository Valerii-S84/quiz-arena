const LOCAL_BACKEND_ORIGIN = "http://localhost:8000";

function readEnv(name: string): string | undefined {
  const value = process.env[name]?.trim();
  return value ? stripTrailingSlash(value) : undefined;
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

function isAbsoluteUrl(value: string): boolean {
  return value.startsWith("http://") || value.startsWith("https://");
}

export function getBrowserApiBaseUrl(): string {
  const configuredUrl = readEnv("NEXT_PUBLIC_API_URL");
  if (configuredUrl) {
    return configuredUrl;
  }

  return process.env.NODE_ENV === "development" ? LOCAL_BACKEND_ORIGIN : "/api";
}

export function getBrowserApiUrl(path: string): string {
  return `${getBrowserApiBaseUrl()}${normalizePath(path)}`;
}

export function getServerApiBaseUrl(): string {
  const internalUrl = readEnv("API_INTERNAL_URL");
  if (internalUrl) {
    return internalUrl;
  }

  const publicUrl = readEnv("NEXT_PUBLIC_API_URL");
  if (publicUrl && isAbsoluteUrl(publicUrl)) {
    return publicUrl;
  }

  return LOCAL_BACKEND_ORIGIN;
}

export function getServerApiUrl(path: string): string {
  return `${getServerApiBaseUrl()}${normalizePath(path)}`;
}
