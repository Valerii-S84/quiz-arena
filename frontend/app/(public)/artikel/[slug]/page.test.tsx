import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import ArticlePage from "./page";

describe("ArticlePage", () => {
  it("renders embedded article HTML inside a sandboxed iframe", async () => {
    render(
      await ArticlePage({
        params: Promise.resolve({ slug: "deutsche-sprache-geschichte" }),
      }),
    );

    const iframe = screen.getByTitle("Geschichte der deutschen Sprache");

    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe.getAttribute("srcdoc")).toContain("embedded-article-theme-override");
  });
});
