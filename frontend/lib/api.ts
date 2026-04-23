import axios from "axios";

import { getBrowserApiBaseUrl } from "@/lib/api-config";
import { apiRoutes } from "@/lib/api-routes";

export const api = axios.create({
  baseURL: getBrowserApiBaseUrl(),
  withCredentials: true,
});

export async function fetchOverview(period: string) {
  const { data } = await api.get(apiRoutes.admin.overview, { params: { period } });
  return data;
}

export async function fetchEconomyPurchases() {
  const { data } = await api.get(apiRoutes.admin.economy.purchases, {
    params: { page: 1, limit: 50 },
  });
  return data;
}

export async function fetchEconomySubscriptions() {
  const { data } = await api.get(apiRoutes.admin.economy.subscriptions, {
    params: { status: "ACTIVE" },
  });
  return data;
}

export async function fetchEconomyCohorts() {
  const { data } = await api.get(apiRoutes.admin.economy.cohorts);
  return data;
}

export type UserListSortBy = "created_at" | "daily_challenge_rating";

type FetchUsersOptions = {
  page?: number;
  limit?: number;
  search?: string;
  sortBy?: UserListSortBy;
};

export async function fetchUsers(options: FetchUsersOptions = {}) {
  const {
    page = 1,
    limit = 100,
    search = "",
    sortBy = "created_at",
  } = options;
  const { data } = await api.get(apiRoutes.admin.users, {
    params: {
      page,
      limit,
      search,
      sort_by: sortBy,
    },
  });
  return data;
}

export async function fetchPromo(status?: string, query?: string) {
  const { data } = await api.get(apiRoutes.admin.promo.list, {
    params: { page: 1, limit: 100, status, query },
  });
  return data;
}

export async function fetchPromoDetail(promoId: number, reveal = false) {
  const { data } = await api.get(apiRoutes.admin.promo.detail(promoId), {
    params: { reveal },
  });
  return data;
}

export async function fetchPromoStats(promoId: number) {
  const { data } = await api.get(apiRoutes.admin.promo.stats(promoId));
  return data;
}

export async function fetchPromoAudit(promoId: number) {
  const { data } = await api.get(apiRoutes.admin.promo.audit(promoId));
  return data;
}

export async function fetchPromoProducts() {
  const { data } = await api.get(apiRoutes.admin.promo.products);
  return data;
}

export async function fetchPromoCodeAvailability(code: string) {
  const { data } = await api.get(apiRoutes.admin.promo.checkCode, {
    params: { code },
  });
  return data;
}

export async function fetchAdminSession() {
  const { data } = await api.get(apiRoutes.admin.auth.session);
  return data;
}

export async function fetchContentHealth() {
  const { data } = await api.get(apiRoutes.admin.content);
  return data;
}

export async function fetchSystemHealth() {
  const { data } = await api.get(apiRoutes.admin.system);
  return data;
}

export async function fetchContactRequests() {
  const { data } = await api.get(apiRoutes.admin.contactRequests.list, {
    params: { page: 1, limit: 20 },
  });
  return data;
}

export async function updateContactRequestStatus(requestId: number, status: string) {
  const { data } = await api.post(apiRoutes.admin.contactRequests.updateStatus(requestId), {
    status,
  });
  return data;
}
