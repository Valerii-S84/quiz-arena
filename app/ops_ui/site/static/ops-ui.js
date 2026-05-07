import { initNotificationsPage } from "./ops-ui-notifications.js";
import { initPromoPage } from "./ops-ui-promo.js";
import { initReferralsPage } from "./ops-ui-referrals.js";

const PAGE_BOOTSTRAP = {
  notifications: initNotificationsPage,
  promo: initPromoPage,
  referrals: initReferralsPage,
};

function bootstrap() {
  const page = document.body.dataset.page;
  const initPage = PAGE_BOOTSTRAP[page];
  if (initPage) {
    initPage();
  }
}

bootstrap();
