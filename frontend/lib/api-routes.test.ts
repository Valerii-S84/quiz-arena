import { describe, expect, it } from "vitest";

import { apiRoutes } from "./api-routes";

describe("api routes", () => {
  it("keeps the public contract on stripped paths behind the browser API base", () => {
    expect(apiRoutes.public.stats).toBe("/stats");
    expect(apiRoutes.public.contact).toBe("/contact");
  });

  it("builds dynamic admin promo and contact-request routes", () => {
    expect(apiRoutes.admin.promo.detail(17)).toBe("/admin/promo/17");
    expect(apiRoutes.admin.promo.stats(17)).toBe("/admin/promo/17/stats");
    expect(apiRoutes.admin.promo.audit(17)).toBe("/admin/promo/17/audit");
    expect(apiRoutes.admin.promo.toggle(17)).toBe("/admin/promo/17/toggle");
    expect(apiRoutes.admin.promo.revoke(17)).toBe("/admin/promo/17/revoke");
    expect(apiRoutes.admin.contactRequests.updateStatus(42)).toBe(
      "/admin/contact-requests/42/status",
    );
  });
});
