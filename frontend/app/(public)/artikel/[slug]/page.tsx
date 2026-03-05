import { readFile } from "node:fs/promises";
import path from "node:path";

type ArticlePageProps = {
  params: {
    slug: string;
  };
};

const ARTICLE_EMBEDS: Record<string, { title: string; src: string; fileName: string }> = {
  "sprachniveaus-a1-c1": {
    title: "Sprachniveaus A1-C1",
    src: "/artikel/sprachniveaus-a1-c1.html",
    fileName: "sprachniveaus-a1-c1.html",
  },
};

export default async function ArticlePage({ params }: ArticlePageProps) {
  const article = ARTICLE_EMBEDS[params.slug];

  if (!article) {
    return (
      <main className="min-h-screen bg-[linear-gradient(135deg,#e8f4f8_0%,#f0f7ee_50%,#fef9f0_100%)] px-4 py-16 text-slate-800 sm:px-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-white/40 bg-white/60 p-8 text-center shadow-[0_4px_24px_rgba(0,0,0,0.06)] backdrop-blur-xl">
          <h1 className="text-3xl font-semibold">Artikel kommt bald</h1>
          <p className="mt-3 text-sm text-slate-600">
            Dieser Bereich wird im nächsten Schritt erweitert.
          </p>
        </div>
      </main>
    );
  }

  let articleHtml = "";
  try {
    articleHtml = await readFile(path.join(process.cwd(), "public", "artikel", article.fileName), "utf-8");
  } catch {
    return (
      <main className="min-h-screen bg-[linear-gradient(135deg,#e8f4f8_0%,#f0f7ee_50%,#fef9f0_100%)] px-4 py-16 text-slate-800 sm:px-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-white/40 bg-white/60 p-8 text-center shadow-[0_4px_24px_rgba(0,0,0,0.06)] backdrop-blur-xl">
          <h1 className="text-3xl font-semibold">Artikel vorübergehend nicht verfügbar</h1>
          <p className="mt-3 text-sm text-slate-600">Bitte versuchen Sie es in einigen Minuten erneut.</p>
        </div>
      </main>
    );
  }

  return (
    <main
      lang="de"
      className="min-h-screen bg-[linear-gradient(135deg,#d7ebf5_0%,#e4f1e0_50%,#f8ecd8_100%)] px-4 py-8 text-slate-900 sm:px-6 sm:py-10"
    >
      <div className="mx-auto max-w-6xl rounded-2xl border border-white/60 bg-white/76 p-4 shadow-[0_10px_30px_rgba(15,23,42,0.10)] backdrop-blur-xl sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <a
            href="/"
            className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 transition hover:bg-slate-50"
          >
            ← Zur Startseite
          </a>
          <a
            href={article.src}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center rounded-full bg-[#E8734A] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#d7653f]"
          >
            Artikel im Vollbild öffnen ↗
          </a>
        </div>

        <iframe
          srcDoc={articleHtml}
          title={article.title}
          loading="lazy"
          className="h-[78vh] w-full rounded-xl border border-slate-200 bg-white sm:h-[84vh]"
        />
      </div>
    </main>
  );
}
