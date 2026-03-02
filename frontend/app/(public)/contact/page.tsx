export const revalidate = 3600;

export default function ContactPage() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-14">
      <h1 className="text-4xl">Контакти</h1>
      <div className="mt-8 space-y-4">
        <a href="https://t.me/quiz_arena_bot" className="surface block rounded-2xl p-5">
          Telegram: @quiz_arena_bot
        </a>
        <a href="mailto:ops@quizarena.local" className="surface block rounded-2xl p-5">
          Email: ops@quizarena.local
        </a>
      </div>
    </main>
  );
}
