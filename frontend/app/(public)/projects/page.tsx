export const revalidate = 3600;

const projects = [
  {
    name: "Telegram Quiz Bot",
    description: "Основний продукт із режимами гри, streak, daily challenge і преміум-економікою.",
  },
  {
    name: "Admin Dashboard",
    description: "Операційна панель для revenue, users, promo, content quality та system health.",
  },
  {
    name: "Analytics Pipeline",
    description: "Щоденні агрегати, публічні метрики та внутрішні алерти для власника.",
  },
];

export default function ProjectsPage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-14">
      <h1 className="text-4xl">Проєкти</h1>
      <div className="mt-8 grid gap-5 sm:grid-cols-3">
        {projects.map((project) => (
          <article key={project.name} className="surface rounded-2xl p-5">
            <h2 className="text-xl">{project.name}</h2>
            <p className="mt-2 text-sm text-ember/70">{project.description}</p>
          </article>
        ))}
      </div>
    </main>
  );
}
