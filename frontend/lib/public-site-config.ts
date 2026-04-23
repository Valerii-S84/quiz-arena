const DEFAULT_TELEGRAM_BOT_URL = "https://t.me/Deine_Deutsch_Quiz_bot";
const DEFAULT_TELEGRAM_CHANNEL_URL = "https://t.me/doechkurse";

function normalizePublicEnv(value: string | undefined): string | undefined {
  const trimmedValue = value?.trim();
  return trimmedValue ? trimmedValue : undefined;
}

export function getTelegramBotUrl(): string {
  return normalizePublicEnv(process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL) ?? DEFAULT_TELEGRAM_BOT_URL;
}

export function getTelegramChannelUrl(): string {
  return (
    normalizePublicEnv(process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_URL) ??
    DEFAULT_TELEGRAM_CHANNEL_URL
  );
}

export const TELEGRAM_BOT_START_PAYLOAD = "site_public_home";
