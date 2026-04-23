import { afterEach, describe, expect, it } from "vitest";

import {
  TELEGRAM_BOT_START_PAYLOAD,
  getTelegramBotUrl,
  getTelegramChannelUrl,
} from "./public-site-config";

const ORIGINAL_TELEGRAM_BOT_URL = process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL;
const ORIGINAL_TELEGRAM_CHANNEL_URL = process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_URL;

function restoreEnv(
  name: "NEXT_PUBLIC_TELEGRAM_BOT_URL" | "NEXT_PUBLIC_TELEGRAM_CHANNEL_URL",
  value: string | undefined,
) {
  if (value === undefined) {
    delete process.env[name];
    return;
  }

  process.env[name] = value;
}

afterEach(() => {
  restoreEnv("NEXT_PUBLIC_TELEGRAM_BOT_URL", ORIGINAL_TELEGRAM_BOT_URL);
  restoreEnv("NEXT_PUBLIC_TELEGRAM_CHANNEL_URL", ORIGINAL_TELEGRAM_CHANNEL_URL);
});

describe("public site config", () => {
  it("uses the default Telegram URLs when env values are unset", () => {
    delete process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL;
    delete process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_URL;

    expect(getTelegramBotUrl()).toBe("https://t.me/Deine_Deutsch_Quiz_bot");
    expect(getTelegramChannelUrl()).toBe("https://t.me/doechkurse");
  });

  it("trims and uses configured Telegram URLs", () => {
    process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL = " https://t.me/custom_bot ";
    process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_URL = " https://t.me/custom_channel ";

    expect(getTelegramBotUrl()).toBe("https://t.me/custom_bot");
    expect(getTelegramChannelUrl()).toBe("https://t.me/custom_channel");
  });

  it("keeps the public home start payload stable", () => {
    expect(TELEGRAM_BOT_START_PAYLOAD).toBe("site_public_home");
  });
});
