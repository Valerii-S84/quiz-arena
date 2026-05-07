import {
  $,
  api,
  buildQuery,
  iso,
  renderCards,
  safeNum,
  showFlash,
} from "./ops-ui-core.js";

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

export function initNotificationsPage() {
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
