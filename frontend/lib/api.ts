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

export async function fetchUsers() {
  const { data } = await api.get("/admin/users", {
    params: { page: 1, limit: 50 },
  });
  return data;
}

export async function fetchPromo(status?: string) {
  const { data } = await api.get("/admin/promo", {
    params: { page: 1, limit: 100, status },
  });
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
