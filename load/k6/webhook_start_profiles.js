import http from "k6/http";
import { check } from "k6";
import { Counter, Rate } from "k6/metrics";

const PROFILE = (__ENV.K6_PROFILE || "steady").trim().toLowerCase();
const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const WEBHOOK_SECRET = __ENV.WEBHOOK_SECRET || "replace_me";
const TELEGRAM_USER_BASE = Number(__ENV.TELEGRAM_USER_BASE || 90000000000);
const UPDATE_ID_BASE = Number(__ENV.UPDATE_ID_BASE || 800000000);

const queuedResponses = new Counter("queued_responses_total");
const ignoredResponses = new Counter("ignored_responses_total");
const invalidResponses = new Counter("invalid_responses_total");
const requestFailures = new Rate("webhook_start_fail_rate");

const PROFILE_CONFIG = {
  steady: {
    executor: "constant-arrival-rate",
    rate: 15,
    timeUnit: "1s",
    duration: "10m",
    preAllocatedVUs: 40,
    maxVUs: 160,
  },
  peak: {
    executor: "ramping-arrival-rate",
    startRate: 10,
    timeUnit: "1s",
    preAllocatedVUs: 60,
    maxVUs: 240,
    stages: [
      { target: 25, duration: "2m" },
      { target: 50, duration: "3m" },
      { target: 80, duration: "3m" },
      { target: 25, duration: "2m" },
    ],
  },
  burst: {
    executor: "ramping-arrival-rate",
    startRate: 10,
    timeUnit: "1s",
    preAllocatedVUs: 80,
    maxVUs: 320,
    stages: [
      { target: 20, duration: "1m" },
      { target: 120, duration: "45s" },
      { target: 20, duration: "2m" },
      { target: 140, duration: "45s" },
      { target: 20, duration: "2m" },
    ],
  },
};

if (!PROFILE_CONFIG[PROFILE]) {
  throw new Error(`Unsupported K6_PROFILE=${PROFILE}. Use steady|peak|burst.`);
}

export const options = {
  scenarios: {
    webhook_start: {
      ...PROFILE_CONFIG[PROFILE],
      exec: "webhookStartFlow",
      tags: { flow: "webhook_start", profile: PROFILE },
    },
  },
  thresholds: {
    "http_req_failed{flow:webhook_start}": ["rate<0.01"],
    "webhook_start_fail_rate{flow:webhook_start}": ["rate<0.01"],
    "http_req_duration{flow:webhook_start}": PROFILE === "burst" ? ["p(95)<500"] : ["p(95)<350"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

function updatePayloadForIteration() {
  const n = (__VU * 1000000) + __ITER;
  const telegramUserId = TELEGRAM_USER_BASE + __VU;
  const updateId = UPDATE_ID_BASE + n;
  return {
    update_id: updateId,
    message: {
      message_id: 1000 + n,
      date: Math.floor(Date.now() / 1000),
      chat: {
        id: telegramUserId,
        type: "private",
        first_name: "Load",
      },
      from: {
        id: telegramUserId,
        is_bot: false,
        first_name: "Load",
        language_code: "de",
      },
      text: "/start",
      entities: [{ offset: 0, length: 6, type: "bot_command" }],
    },
  };
}

export function webhookStartFlow() {
  const payload = updatePayloadForIteration();
  const response = http.post(
    `${BASE_URL}/webhook/telegram`,
    JSON.stringify(payload),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET,
      },
      tags: { flow: "webhook_start", profile: PROFILE },
    },
  );

  const ok = check(response, {
    "status is 200": (r) => r.status === 200,
    "webhook status is queued|ignored": (r) => {
      try {
        const body = r.json();
        return body && (body.status === "queued" || body.status === "ignored");
      } catch (_err) {
        return false;
      }
    },
  });
  requestFailures.add(!ok, { flow: "webhook_start", profile: PROFILE });

  try {
    const body = response.json();
    if (body.status === "queued") {
      queuedResponses.add(1, { flow: "webhook_start", profile: PROFILE });
    } else if (body.status === "ignored") {
      ignoredResponses.add(1, { flow: "webhook_start", profile: PROFILE });
    } else {
      invalidResponses.add(1, { flow: "webhook_start", profile: PROFILE });
    }
  } catch (_err) {
    invalidResponses.add(1, { flow: "webhook_start", profile: PROFILE });
  }
}
