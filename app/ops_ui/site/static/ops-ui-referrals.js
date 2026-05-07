import {
  $,
  api,
  buildQuery,
  createActionButton,
  iso,
  pct,
  renderCards,
  safeNum,
  showFlash,
} from "./ops-ui-core.js";

function renderReviewRow(tbody, row, onDecision) {
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
      onClick: () => onDecision(row.referral_id, "CONFIRM_FRAUD", row.status),
    })
  );
  actions.appendChild(
    createActionButton({
      label: "Reopen",
      className: "ok",
      onClick: () => onDecision(row.referral_id, "REOPEN", row.status),
    })
  );
  actions.appendChild(
    createActionButton({
      label: "Cancel",
      className: "ghost",
      onClick: () => onDecision(row.referral_id, "CANCEL", row.status),
    })
  );

  tr.appendChild(actions);
  tbody.appendChild(tr);
}

export function initReferralsPage() {
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
      const data = await api(
        `/internal/referrals/dashboard${buildQuery({ window_hours: dashboardWindow.value })}`
      );
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

  async function loadQueue() {
    if (!reviewTbody) return;
    try {
      const query = buildQuery({
        window_hours: reviewWindow.value,
        status: reviewStatus.value,
        limit: reviewLimit.value,
      });
      const data = await api(`/internal/referrals/review-queue${query}`);
      reviewTbody.innerHTML = "";
      data.cases.forEach((row) => renderReviewRow(reviewTbody, row, applyDecision));
    } catch (error) {
      showFlash(`Queue error: ${error.message}`, "err");
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

  dashboardButton.addEventListener("click", loadDashboard);
  reviewButton.addEventListener("click", loadQueue);
  loadDashboard();
  loadQueue();
}
