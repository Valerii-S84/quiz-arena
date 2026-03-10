import { readFile } from "node:fs/promises";
import path from "node:path";
import { notFound } from "next/navigation";

type ArticlePageProps = {
  params: {
    slug: string;
  };
};

const ARTICLE_EMBEDS: Record<string, { title: string; fileName: string }> = {
  "deutsche-sprache-geschichte": {
    title: "Geschichte der deutschen Sprache",
    fileName: "deutsche-sprache-geschichte.html",
  },
  "pruefungen-goethe-telc-testdaf": {
    title: "Prüfungen: Goethe / telc / TestDaF",
    fileName: "pruefungen-goethe-telc-testdaf.html",
  },
  "sprachniveaus-a1-c1": {
    title: "Sprachniveaus A1-C1",
    fileName: "sprachniveaus-a1-c1.html",
  },
};

export const dynamicParams = false;

export function generateStaticParams() {
  return Object.keys(ARTICLE_EMBEDS).map((slug) => ({ slug }));
}
function applyEmbeddedTheme(html: string): string {
  const embedThemeOverride = `
<style id="embedded-article-theme-override">
  :root {
    --bg: #cedde8;
    --surface: #f4f7fa;
    --border: #b8cad6;
    --text: #132233;
    --muted: #31465b;
    --accent: #e8734a;
    --a0-bg: rgba(155,155,155,0.14);
    --a1-bg: rgba(110,198,224,0.14);
    --a2-bg: rgba(77,184,168,0.14);
    --b1-bg: rgba(126,200,110,0.14);
    --b2-bg: rgba(200,184,78,0.14);
    --c1-bg: rgba(224,120,72,0.14);
    --c2-bg: rgba(208,72,112,0.14);
  }
  body {
    background: linear-gradient(135deg, #b7d1df 0%, #c4d7bf 50%, #dbcfbf 100%) !important;
    color: var(--text) !important;
    font-weight: 400 !important;
  }
  .card-block,
  .tip-card,
  .ag-cell,
  .cefr-group,
  .notice,
  .time-badge,
  .exams-table th {
    background: rgba(255, 255, 255, 0.97) !important;
  }
  .card-description,
  .tip-desc,
  .ag-desc,
  .cefr-group-sub,
  .card-subtitle {
    color: #3f556a !important;
  }
  .exams-table tr:hover td {
    background: rgba(15, 23, 42, 0.06) !important;
  }
</style>`;
  if (html.includes("</head>")) {
    return html.replace("</head>", `${embedThemeOverride}</head>`);
  }
  return `${embedThemeOverride}${html}`;
}

export default async function ArticlePage({ params }: ArticlePageProps) {
  const article = ARTICLE_EMBEDS[params.slug];

  if (!article) {
    notFound();
  }

  let articleHtml = "";
  try {
    articleHtml = await readFile(path.join(process.cwd(), "public", "artikel", article.fileName), "utf-8");
    articleHtml = applyEmbeddedTheme(articleHtml);
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
      className="min-h-screen bg-[linear-gradient(135deg,#c1d8e5_0%,#cde0c7_50%,#e0d5c5_100%)] text-slate-900"
    >
      <div className="sticky top-0 z-20 border-b border-white/60 bg-white/82 px-4 py-3 backdrop-blur sm:px-6">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-start">
          <a
            href="/"
            className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 transition hover:bg-slate-50"
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
