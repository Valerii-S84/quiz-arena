import { readFile } from "node:fs/promises";
import path from "node:path";

type ArticlePageProps = {
  params: {
    slug: string;
  };
};

const ARTICLE_EMBEDS: Record<string, { title: string; fileName: string }> = {
  "sprachniveaus-a1-c1": {
    title: "Sprachniveaus A1-C1",
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
      className="min-h-screen bg-[#0f0f13] text-slate-100"
    >
      <div className="sticky top-0 z-20 border-b border-white/10 bg-[#0f0f13]/95 px-4 py-3 backdrop-blur sm:px-6">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-start">
          <a
            href="/"
            className="inline-flex items-center rounded-full border border-white/25 bg-white/10 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/20"
          >
            ← Zur Startseite
          </a>
        </div>
      </div>

      <iframe
        srcDoc={articleHtml}
        title={article.title}
        loading="lazy"
        className="block h-[calc(100vh-61px)] w-full border-0 bg-white"
      />
    </main>
  );
}
