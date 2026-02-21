(function () {
  function $(id) {
    return document.getElementById(id);
  }

  function safeNum(value, digits = 0) {
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return "0";
    }
    return num.toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function pct(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return "0.0%";
    }
    return `${(num * 100).toFixed(1)}%`;
  }

  function iso(value) {
    if (!value) {
      return "-";
    }
    try {
      return new Date(value).toLocaleString();
    } catch {
      return String(value);
    }
  }

  function showFlash(message, kind = "ok") {
    const flash = $("flash");
    if (!flash) {
      return;
    }
    flash.textContent = message;
    flash.className = `flash ${kind} show`;
    window.setTimeout(() => {
      flash.className = "flash";
    }, 2600);
  }

  function buildQuery(params) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") {
        return;
      }
      search.set(key, String(value));
    });
    const encoded = search.toString();
    return encoded ? `?${encoded}` : "";
  }

  async function api(path, options = {}) {
    const init = {
      method: options.method || "GET",
      headers: {},
      credentials: "same-origin",
    };

    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }

    const response = await fetch(path, init);
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const code = payload && payload.detail && payload.detail.code ? payload.detail.code : `HTTP_${response.status}`;
      if (response.status === 403) {
        window.location.assign("/ops/login");
      }
      throw new Error(code);
    }

    return payload;
  }

  function renderCards(target, cards) {
    if (!target) {
      return;
    }
    target.innerHTML = "";
    cards.forEach((card) => {
      const article = document.createElement("article");
      article.className = "card";

      const label = document.createElement("p");
      label.className = "label";
      label.textContent = card.label;

      const value = document.createElement("p");
      value.className = "value";
      value.textContent = card.value;

      article.append(label, value);
      target.appendChild(article);
    });
  }

  function createActionButton({ label, className, onClick }) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `tiny ${className || "ghost"}`;
    btn.textContent = label;
    btn.addEventListener("click", onClick);
    return btn;
  }

  function renderJson(target, payload) {
    if (!target) {
      return;
    }
    target.textContent = JSON.stringify(payload, null, 2);
  }

  function initPromoPage() {
    const dashboardCards = $("promo-dashboard-cards");
    const dashboardWindow = $("promo-window-hours");
    const dashboardButton = $("promo-refresh-dashboard");

    const campaignStatus = $("promo-campaign-status");
    const campaignName = $("promo-campaign-name");
    const campaignLimit = $("promo-campaign-limit");
    const campaignButton = $("promo-refresh-campaigns");
    const campaignTbody = document.querySelector("#promo-campaigns-table tbody");

    const rollbackPurchaseId = $("promo-purchase-id");
    const rollbackReason = $("promo-rollback-reason");
    const rollbackButton = $("promo-run-rollback");
    const rollbackResult = $("promo-rollback-result");

    async function loadDashboard() {
      try {
        const data = await api(`/internal/promo/dashboard${buildQuery({ window_hours: dashboardWindow.value })}`);
        renderCards(dashboardCards, [
          { label: "Attempts", value: safeNum(data.attempts_total) },
          { label: "Acceptance", value: pct(data.acceptance_rate) },
          { label: "Failure", value: pct(data.failure_rate) },
          { label: "Applied redemptions", value: safeNum(data.redemptions_applied) },
          { label: "Discount conversion", value: pct(data.discount_conversion_rate) },
          { label: "Guard hashes", value: safeNum(data.guard_trigger_hashes) },
          { label: "Active campaigns", value: safeNum(data.active_campaigns_total) },
          { label: "Paused campaigns", value: safeNum(data.paused_campaigns_total) },
        ]);
      } catch (error) {
        showFlash(`Dashboard error: ${error.message}`, "err");
      }
    }

    async function loadCampaigns() {
      if (!campaignTbody) {
        return;
      }
      try {
        const query = buildQuery({
          status: campaignStatus.value,
          campaign_name: campaignName.value.trim(),
          limit: campaignLimit.value,
        });
        const data = await api(`/internal/promo/campaigns${query}`);
        campaignTbody.innerHTML = "";

        data.campaigns.forEach((row) => {
          const tr = document.createElement("tr");
          const maxUses = row.max_total_uses === null ? "∞" : safeNum(row.max_total_uses);

          const fields = [
            row.id,
            row.campaign_name,
            row.promo_type,
            row.status,
            row.target_scope,
            `${safeNum(row.used_total)} / ${maxUses}`,
            iso(row.valid_until),
          ];

          fields.forEach((value) => {
            const td = document.createElement("td");
            td.textContent = String(value);
            tr.appendChild(td);
          });

          const actionTd = document.createElement("td");
          if (row.status === "ACTIVE" || row.status === "PAUSED") {
            const desired = row.status === "ACTIVE" ? "PAUSED" : "ACTIVE";
            const button = createActionButton({
              label: desired === "PAUSED" ? "Pause" : "Activate",
              className: desired === "PAUSED" ? "warn" : "ok",
              onClick: async () => {
                const reason = window.prompt(`Reason for switching to ${desired}? (optional)`, "") || "";
                try {
                  await api(`/internal/promo/campaigns/${row.id}/status`, {
                    method: "POST",
                    body: {
                      status: desired,
                      reason,
                      expected_current_status: row.status,
                    },
                  });
                  showFlash(`Campaign ${row.id} -> ${desired}`, "ok");
                  await loadCampaigns();
                  await loadDashboard();
                } catch (error) {
                  showFlash(`Status update failed: ${error.message}`, "err");
                }
              },
            });
            actionTd.appendChild(button);
          } else {
            actionTd.textContent = "-";
          }

          tr.appendChild(actionTd);
          campaignTbody.appendChild(tr);
        });
      } catch (error) {
        showFlash(`Campaigns error: ${error.message}`, "err");
      }
    }

    async function runRollback() {
      const purchaseId = rollbackPurchaseId.value.trim();
      if (!purchaseId) {
        showFlash("Purchase UUID is required", "err");
        return;
      }
      try {
        const data = await api("/internal/promo/refund-rollback", {
          method: "POST",
          body: {
            purchase_id: purchaseId,
            reason: rollbackReason.value.trim() || null,
          },
        });
        renderJson(rollbackResult, data);
        showFlash("Rollback completed", "ok");
      } catch (error) {
        renderJson(rollbackResult, { error: error.message });
        showFlash(`Rollback failed: ${error.message}`, "err");
      }
    }

    dashboardButton.addEventListener("click", loadDashboard);
    campaignButton.addEventListener("click", loadCampaigns);
    rollbackButton.addEventListener("click", runRollback);

    loadDashboard();
    loadCampaigns();
  }

  function initReferralsPage() {
    const dashboardCards = $("ref-dashboard-cards");
    const dashboardWindow = $("ref-window-hours");
    const dashboardButton = $("ref-refresh-dashboard");

    const reviewWindow = $("ref-review-window-hours");
    const reviewStatus = $("ref-review-status");
    const reviewLimit = $("ref-review-limit");
    const reviewButton = $("ref-refresh-queue");
    const reviewTbody = document.querySelector("#ref-review-table tbody");

    async function loadDashboard() {
      try {
        const data = await api(`/internal/referrals/dashboard${buildQuery({ window_hours: dashboardWindow.value })}`);
        renderCards(dashboardCards, [
          { label: "Starts", value: safeNum(data.referrals_started_total) },
          { label: "Qualified-like", value: safeNum(data.qualified_like_total) },
          { label: "Rewarded", value: safeNum(data.rewarded_total) },
          { label: "Fraud rejected", value: safeNum(data.rejected_fraud_total) },
          { label: "Qualification rate", value: pct(data.qualification_rate) },
          { label: "Reward rate", value: pct(data.reward_rate) },
          { label: "Fraud rate", value: pct(data.fraud_rejected_rate) },
          { label: "Fraud spike", value: data.alerts.fraud_spike_detected ? "YES" : "NO" },
        ]);
      } catch (error) {
        showFlash(`Dashboard error: ${error.message}`, "err");
      }
    }

    async function applyDecision(referralId, decision, expectedStatus) {
      const reason = window.prompt(`Reason for ${decision}? (optional)`, "") || "";
      try {
        await api(`/internal/referrals/${referralId}/review`, {
          method: "POST",
          body: {
            decision,
            reason,
            expected_current_status: expectedStatus,
          },
        });
        showFlash(`Referral ${referralId}: ${decision}`, "ok");
        await loadQueue();
        await loadDashboard();
      } catch (error) {
        showFlash(`Decision failed: ${error.message}`, "err");
      }
    }

    async function loadQueue() {
      if (!reviewTbody) {
        return;
      }
      try {
        const query = buildQuery({
          window_hours: reviewWindow.value,
          status: reviewStatus.value,
          limit: reviewLimit.value,
        });
        const data = await api(`/internal/referrals/review-queue${query}`);

        reviewTbody.innerHTML = "";
        data.cases.forEach((row) => {
          const tr = document.createElement("tr");
          const fields = [
            row.referral_id,
            row.referrer_user_id,
            row.referred_user_id,
            row.status,
            safeNum(row.fraud_score, 2),
            iso(row.created_at),
          ];
          fields.forEach((value) => {
            const td = document.createElement("td");
            td.textContent = String(value);
            tr.appendChild(td);
          });

          const actions = document.createElement("td");
          actions.appendChild(
            createActionButton({
              label: "Confirm Fraud",
              className: "warn",
              onClick: () => applyDecision(row.referral_id, "CONFIRM_FRAUD", row.status),
            })
          );
          actions.appendChild(
            createActionButton({
              label: "Reopen",
              className: "ok",
              onClick: () => applyDecision(row.referral_id, "REOPEN", row.status),
            })
          );
          actions.appendChild(
            createActionButton({
              label: "Cancel",
              className: "ghost",
              onClick: () => applyDecision(row.referral_id, "CANCEL", row.status),
            })
          );

          tr.appendChild(actions);
          reviewTbody.appendChild(tr);
        });
      } catch (error) {
        showFlash(`Queue error: ${error.message}`, "err");
      }
    }

    dashboardButton.addEventListener("click", loadDashboard);
    reviewButton.addEventListener("click", loadQueue);

    loadDashboard();
    loadQueue();
  }

  function renderNotificationsFeed(container, events) {
    if (!container) {
      return;
    }
    container.innerHTML = "";
    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No events in selected window.";
      container.appendChild(empty);
      return;
    }

    events.forEach((event) => {
      const item = document.createElement("article");
      item.className = "event-item";

      const meta = document.createElement("div");
      meta.className = "event-meta";

      const type = document.createElement("span");
      type.className = "event-type";
      type.textContent = event.event_type;

      const status = document.createElement("span");
      status.className = `pill ${event.status === "SENT" ? "ok" : "err"}`;
      status.textContent = event.status;

      const createdAt = document.createElement("span");
      createdAt.textContent = iso(event.created_at);

      const eventId = document.createElement("span");
      eventId.className = "mono";
      eventId.textContent = `#${event.id}`;

      meta.append(type, status, createdAt, eventId);

      const payload = document.createElement("pre");
      payload.className = "json-view event-payload";
      payload.textContent = JSON.stringify(event.payload || {}, null, 2);

      item.append(meta, payload);
      container.appendChild(item);
    });
  }

  function initNotificationsPage() {
    const summary = $("notif-summary");
    const feed = $("notif-events");

    const windowHours = $("notif-window-hours");
    const eventType = $("notif-event-type");
    const limit = $("notif-limit");
    const button = $("notif-refresh");

    async function loadFeed() {
      try {
        const query = buildQuery({
          window_hours: windowHours.value,
          event_type: eventType.value,
          limit: limit.value,
        });
        const data = await api(`/internal/referrals/events${query}`);
        renderCards(summary, [
          { label: "Total events", value: safeNum(data.total_events) },
          { label: "Sent", value: safeNum(data.by_status.SENT || 0) },
          { label: "Failed", value: safeNum(data.by_status.FAILED || 0) },
          {
            label: "Milestone",
            value: safeNum(data.by_type.referral_reward_milestone_available || 0),
          },
          {
            label: "Granted",
            value: safeNum(data.by_type.referral_reward_granted || 0),
          },
        ]);
        renderNotificationsFeed(feed, data.events || []);
      } catch (error) {
        showFlash(`Feed error: ${error.message}`, "err");
      }
    }

    button.addEventListener("click", loadFeed);
    loadFeed();
  }

  function bootstrap() {
    const page = document.body.dataset.page;
    if (page === "promo") {
      initPromoPage();
      return;
    }
    if (page === "referrals") {
      initReferralsPage();
      return;
    }
    if (page === "notifications") {
      initNotificationsPage();
    }
  }

  bootstrap();
})();
