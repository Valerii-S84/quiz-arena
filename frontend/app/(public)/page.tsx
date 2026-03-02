export const revalidate = 3600;

type PublicMetrics = {
  users_total: number;
  quizzes_total: number;
  purchases_total: number;
  revenue_stars_total: number;
};

async function getMetrics(): Promise<PublicMetrics> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const response = await fetch(`${baseUrl}/public/metrics`, {
      next: { revalidate: 3600 },
    });
    if (response.ok) {
      return response.json();
    }
  } catch {
    return {
      users_total: 0,
      quizzes_total: 0,
      purchases_total: 0,
      revenue_stars_total: 0,
    };
  }
  return {
    users_total: 0,
    quizzes_total: 0,
    purchases_total: 0,
    revenue_stars_total: 0,
  };
}

const products = [
  { title: "Quiz Arena Bot", text: "Навчальні квізи, streak-механіки та змагання в Telegram." },
  { title: "Promo Ops", text: "Керування промокодами, bulk-генерація та контроль використань." },
  { title: "Analytics Core", text: "DAU/WAU/MAU, конверсії та алерти для операційних рішень." },
];

export default async function PublicHomePage() {
  const metrics = await getMetrics();

  return (
    <main className="mx-auto max-w-6xl px-6 py-14">
      <section className="fade-in rounded-3xl border border-ember/15 bg-white/70 p-8 shadow-sm">
        <p className="text-sm uppercase tracking-[0.2em] text-ocean">Quiz Arena</p>
        <h1 className="mt-3 text-4xl leading-tight sm:text-5xl">Bot Operations & Analytics Dashboard</h1>
        <p className="mt-5 max-w-2xl text-lg text-ember/80">
          Публічна вітрина продуктів і операційна адмін-панель для контролю економіки, користувачів,
          промо та стабільності сервісу.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <a href="/projects" className="rounded-full bg-ember px-5 py-2 text-sand">Проєкти</a>
          <a href="/contact" className="rounded-full border border-ember/30 px-5 py-2">Контакти</a>
          <a href="/admin/login" className="rounded-full bg-coral px-5 py-2 text-ember">Admin Login</a>
        </div>
      </section>

      <section className="mt-10 grid gap-4 sm:grid-cols-3">
        {products.map((item) => (
          <article key={item.title} className="surface rounded-2xl p-5 fade-in">
            <h2 className="text-xl">{item.title}</h2>
            <p className="mt-2 text-sm text-ember/75">{item.text}</p>
          </article>
        ))}
      </section>

      <section className="mt-10 grid gap-4 sm:grid-cols-4">
        <div className="surface rounded-2xl p-5">
          <p className="text-xs uppercase tracking-widest text-ember/60">Users</p>
          <p className="mt-2 text-3xl font-semibold">{metrics.users_total.toLocaleString("uk-UA")}</p>
        </div>
        <div className="surface rounded-2xl p-5">
          <p className="text-xs uppercase tracking-widest text-ember/60">Quizzes</p>
          <p className="mt-2 text-3xl font-semibold">{metrics.quizzes_total.toLocaleString("uk-UA")}</p>
        </div>
        <div className="surface rounded-2xl p-5">
          <p className="text-xs uppercase tracking-widest text-ember/60">Purchases</p>
          <p className="mt-2 text-3xl font-semibold">{metrics.purchases_total.toLocaleString("uk-UA")}</p>
        </div>
        <div className="surface rounded-2xl p-5">
          <p className="text-xs uppercase tracking-widest text-ember/60">Revenue (Stars)</p>
          <p className="mt-2 text-3xl font-semibold">{metrics.revenue_stars_total.toLocaleString("uk-UA")}</p>
        </div>
      </section>

      <footer className="mt-12 border-t border-ember/10 py-6 text-sm text-ember/70">
        Quiz Arena Operations • Telegram Bot Analytics Suite
      </footer>
    </main>
  );
}
