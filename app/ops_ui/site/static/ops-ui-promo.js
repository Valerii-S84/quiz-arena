import {
  $,
  api,
  buildQuery,
  createActionButton,
  iso,
  pct,
  renderCards,
  renderJson,
  safeNum,
  showFlash,
} from "./ops-ui-core.js";

function promoTypeLabel(value) {
  if (value === "PERCENT_DISCOUNT") return "Prozent-Rabatt";
  if (value === "PREMIUM_GRANT") return "Arena-Pass-Tage";
  return String(value || "-");
}

function promoStatusLabel(value) {
  if (value === "ACTIVE") return "Aktiv";
  if (value === "PAUSED") return "Pausiert";
  if (value === "EXPIRED") return "Abgelaufen";
  if (value === "DEPLETED") return "Aufgebraucht";
  return String(value || "-");
}

function promoScopeLabel(value) {
  if (value === "ANY") return "Alle Produkte";
  if (value === "MICRO_ANY") return "Mikro-Pakete";
  if (value === "PREMIUM_ANY") return "Arena Pass Pläne";
  if (value === "ENERGY_10") return "+10 Energie";
  if (value === "STREAK_SAVER_20") return "Serien-Schutz";
  if (value === "FRIEND_CHALLENGE_5") return "Duell-Ticket";
  if (value === "PREMIUM_3_DAYS") return "Arena Pass 3 Tage";
  if (value === "PREMIUM_WEEK") return "Arena Pass 7 Tage";
  if (value === "PREMIUM_MONTH") return "Arena Pass 30 Tage";
  if (value === "PREMIUM_SEASON") return "Arena Pass Saison";
  if (value === "PREMIUM_YEAR") return "Arena Pass Jahr";
  return String(value || "-");
}

function renderCampaignRow(tbody, row, onStatusChange) {
  const tr = document.createElement("tr");
  const maxUses = row.max_total_uses === null ? "∞" : safeNum(row.max_total_uses);
  const fields = [
    row.id,
    row.campaign_name,
    promoTypeLabel(row.promo_type),
    promoStatusLabel(row.status),
    promoScopeLabel(row.target_scope),
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
    actionTd.appendChild(
      createActionButton({
        label: desired === "PAUSED" ? "Pausieren" : "Aktivieren",
        className: desired === "PAUSED" ? "warn" : "ok",
        onClick: () => onStatusChange(row, desired),
      })
    );
  } else {
    actionTd.textContent = "-";
  }

  tr.appendChild(actionTd);
  tbody.appendChild(tr);
}

export function initPromoPage() {
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
      const data = await api(
        `/internal/promo/dashboard${buildQuery({ window_hours: dashboardWindow.value })}`
      );
      renderCards(dashboardCards, [
        { label: "Versuche", value: safeNum(data.attempts_total) },
        { label: "Akzeptanz", value: pct(data.acceptance_rate) },
        { label: "Fehlerquote", value: pct(data.failure_rate) },
        { label: "Eingeloeste Einloesungen", value: safeNum(data.redemptions_applied) },
        { label: "Rabatt-Konversion", value: pct(data.discount_conversion_rate) },
        { label: "Ausgeloeste Schutz-Hashes", value: safeNum(data.guard_trigger_hashes) },
        { label: "Aktive Kampagnen", value: safeNum(data.active_campaigns_total) },
        { label: "Pausierte Kampagnen", value: safeNum(data.paused_campaigns_total) },
      ]);
    } catch (error) {
      showFlash(`Fehler beim Laden der Uebersicht: ${error.message}`, "err");
    }
  }

  async function updateCampaignStatus(row, desired) {
    const reason =
      window.prompt(`Grund für Wechsel zu ${promoStatusLabel(desired)}? (optional)`, "") || "";
    try {
      await api(`/internal/promo/campaigns/${row.id}/status`, {
        method: "POST",
        body: {
          status: desired,
          reason,
          expected_current_status: row.status,
        },
      });
      showFlash(`Kampagne ${row.id} -> ${promoStatusLabel(desired)}`, "ok");
      await loadCampaigns();
      await loadDashboard();
    } catch (error) {
      showFlash(`Status-Update fehlgeschlagen: ${error.message}`, "err");
    }
  }

  async function loadCampaigns() {
    if (!campaignTbody) return;
    try {
      const query = buildQuery({
        status: campaignStatus.value,
        campaign_name: campaignName.value.trim(),
        limit: campaignLimit.value,
      });
      const data = await api(`/internal/promo/campaigns${query}`);
      campaignTbody.innerHTML = "";
      data.campaigns.forEach((row) => {
        renderCampaignRow(campaignTbody, row, updateCampaignStatus);
      });
    } catch (error) {
      showFlash(`Fehler beim Laden der Kampagnen: ${error.message}`, "err");
    }
  }

  async function runRollback() {
    const purchaseId = rollbackPurchaseId.value.trim();
    if (!purchaseId) {
      showFlash("Kauf-UUID ist erforderlich", "err");
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
      showFlash("Rollback abgeschlossen", "ok");
    } catch (error) {
      renderJson(rollbackResult, { error: error.message });
      showFlash(`Rollback fehlgeschlagen: ${error.message}`, "err");
    }
  }

  dashboardButton.addEventListener("click", loadDashboard);
  campaignButton.addEventListener("click", loadCampaigns);
  rollbackButton.addEventListener("click", runRollback);
  loadDashboard();
  loadCampaigns();
}
