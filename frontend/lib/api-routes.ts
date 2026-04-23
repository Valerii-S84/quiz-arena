export const apiRoutes = {
  public: {
    stats: "/stats",
    contact: "/contact",
  },
  admin: {
    overview: "/admin/overview",
    economy: {
      purchases: "/admin/economy/purchases",
      subscriptions: "/admin/economy/subscriptions",
      cohorts: "/admin/economy/cohorts",
    },
    users: "/admin/users",
    promo: {
      list: "/admin/promo",
      detail: (promoId: number) => `/admin/promo/${promoId}`,
      stats: (promoId: number) => `/admin/promo/${promoId}/stats`,
      audit: (promoId: number) => `/admin/promo/${promoId}/audit`,
      products: "/admin/promo/products",
      checkCode: "/admin/promo/check-code",
      bulkGenerate: "/admin/promo/bulk-generate",
      toggle: (promoId: number) => `/admin/promo/${promoId}/toggle`,
      revoke: (promoId: number) => `/admin/promo/${promoId}/revoke`,
    },
    auth: {
      login: "/admin/auth/login",
      verify2FA: "/admin/auth/2fa/verify",
      session: "/admin/auth/session",
      logout: "/admin/auth/logout",
    },
    content: "/admin/content",
    system: "/admin/system",
    contactRequests: {
      list: "/admin/contact-requests",
      updateStatus: (requestId: number) => `/admin/contact-requests/${requestId}/status`,
    },
  },
} as const;
