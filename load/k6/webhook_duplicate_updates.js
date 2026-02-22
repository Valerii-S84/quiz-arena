import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const WEBHOOK_SECRET = __ENV.WEBHOOK_SECRET || "replace_me";
const TELEGRAM_USER_BASE = Number(__ENV.TELEGRAM_USER_BASE || 91000000000);
const UPDATE_ID_BASE = Number(__ENV.UPDATE_ID_BASE || 810000000);

const duplicateRequestFailures = new Rate("webhook_duplicate_fail_rate");

export const options = {
  scenarios: {
    duplicate_burst: {
      executor: "constant-vus",
      vus: Number(__ENV.DUPLICATE_VUS || 40),
      duration: __ENV.DUPLICATE_DURATION || "5m",
      exec: "duplicateUpdateFlow",
      tags: { flow: "webhook_duplicates" },
    },
  },
  thresholds: {
    "http_req_failed{flow:webhook_duplicates}": ["rate<0.01"],
    "webhook_duplicate_fail_rate{flow:webhook_duplicates}": ["rate<0.01"],
    "http_req_duration{flow:webhook_duplicates}": ["p(95)<500"],
  },
};

function messagePayload({ updateId, telegramUserId, messageId }) {
  return {
    update_id: updateId,
    message: {
      message_id: messageId,
      date: Math.floor(Date.now() / 1000),
      chat: {
        id: telegramUserId,
        type: "private",
        first_name: "Dup",
      },
      from: {
        id: telegramUserId,
        is_bot: false,
        first_name: "Dup",
        language_code: "de",
      },
      text: "/start",
      entities: [{ offset: 0, length: 6, type: "bot_command" }],
    },
  };
}

function postWebhook(payload) {
  return http.post(
    `${BASE_URL}/webhook/telegram`,
    JSON.stringify(payload),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET,
      },
      tags: { flow: "webhook_duplicates" },
    },
  );
}

export function duplicateUpdateFlow() {
  const n = (__VU * 1000000) + __ITER;
  const telegramUserId = TELEGRAM_USER_BASE + __VU;
  const updateId = UPDATE_ID_BASE + n;
  const baseMessageId = 2000 + n;

  const payload = messagePayload({
    updateId,
    telegramUserId,
    messageId: baseMessageId,
  });

  const first = postWebhook(payload);
  const second = postWebhook(payload);

  const ok = check(first, {
    "first duplicate request is 200": (r) => r.status === 200,
  }) && check(second, {
    "second duplicate request is 200": (r) => r.status === 200,
  });
  duplicateRequestFailures.add(!ok, { flow: "webhook_duplicates" });

  sleep(0.2);
}
