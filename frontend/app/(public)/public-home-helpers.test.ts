import { describe, expect, it } from "vitest";

import { buildTrackedTelegramBotUrl } from "./public-home-helpers";

describe("public home helpers", () => {
  it("adds the tracking payload to a valid Telegram URL", () => {
    expect(
      buildTrackedTelegramBotUrl(
        "https://t.me/Deine_Deutsch_Quiz_bot?source=site",
        "site_public_home",
      ),
    ).toBe("https://t.me/Deine_Deutsch_Quiz_bot?source=site&start=site_public_home");
  });

  it("falls back to string concatenation for invalid URLs", () => {
    expect(buildTrackedTelegramBotUrl("not-a-valid-url", "site_public_home")).toBe(
      "not-a-valid-url?start=site_public_home",
    );
  });
});
