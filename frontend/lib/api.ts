import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

export async function fetchOverview(period: string) {
  const { data } = await api.get("/admin/overview", { params: { period } });
  return data;
}

export async function fetchEconomyPurchases() {
  const { data } = await api.get("/admin/economy/purchases", {
    params: { page: 1, limit: 50 },
  });
  return data;
}

export async function fetchEconomySubscriptions() {
  const { data } = await api.get("/admin/economy/subscriptions", {
    params: { status: "ACTIVE" },
  });
  return data;
}

export async function fetchEconomyCohorts() {
  const { data } = await api.get("/admin/economy/cohorts");
  return data;
}

export async function fetchUsers() {
  const { data } = await api.get("/admin/users", {
    params: { page: 1, limit: 50 },
  });
  return data;
}

export async function fetchPromo(status?: string, query?: string) {
  const { data } = await api.get("/admin/promo", {
    params: { page: 1, limit: 100, status, query },
  });
  return data;
}

export async function fetchPromoDetail(promoId: number, reveal = false) {
  const { data } = await api.get(`/admin/promo/${promoId}`, {
    params: { reveal },
  });
  return data;
}

export async function fetchPromoStats(promoId: number) {
  const { data } = await api.get(`/admin/promo/${promoId}/stats`);
  return data;
}

export async function fetchPromoAudit(promoId: number) {
  const { data } = await api.get(`/admin/promo/${promoId}/audit`);
  return data;
}

export async function fetchPromoProducts() {
  const { data } = await api.get("/admin/promo/products");
  return data;
}

export async function fetchPromoCodeAvailability(code: string) {
  const { data } = await api.get("/admin/promo/check-code", {
    params: { code },
  });
  return data;
}

export async function fetchAdminSession() {
  const { data } = await api.get("/admin/auth/session");
  return data;
}

export async function fetchContentHealth() {
  const { data } = await api.get("/admin/content");
  return data;
}

export async function fetchSystemHealth() {
  const { data } = await api.get("/admin/system");
  return data;
}

export async function fetchContactRequests() {
  const { data } = await api.get("/admin/contact-requests", {
    params: { page: 1, limit: 20 },
  });
  return data;
}

export async function updateContactRequestStatus(requestId: number, status: string) {
  const { data } = await api.post(`/admin/contact-requests/${requestId}/status`, {
    status,
  });
  return data;
}
