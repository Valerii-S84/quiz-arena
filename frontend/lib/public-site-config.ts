const DEFAULT_TELEGRAM_BOT_URL = "https://t.me/Deine_Deutsch_Quiz_bot";
const DEFAULT_TELEGRAM_CHANNEL_URL = "https://t.me/doechkurse";

function readPublicEnv(name: string): string | undefined {
  const value = process.env[name]?.trim();
  return value ? value : undefined;
}

export function getTelegramBotUrl(): string {
  return readPublicEnv("NEXT_PUBLIC_TELEGRAM_BOT_URL") ?? DEFAULT_TELEGRAM_BOT_URL;
}

export function getTelegramChannelUrl(): string {
  return readPublicEnv("NEXT_PUBLIC_TELEGRAM_CHANNEL_URL") ?? DEFAULT_TELEGRAM_CHANNEL_URL;
}

export const TELEGRAM_BOT_START_PAYLOAD = "site_public_home";
