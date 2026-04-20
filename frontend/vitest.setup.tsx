import { cleanup } from "@testing-library/react";
import React from "react";
import { afterEach, beforeAll, vi } from "vitest";

vi.mock("next/font/google", () => ({
  Inter: () => ({ className: "mock-inter-font" }),
}));

vi.mock("next/image", () => ({
  default: function MockNextImage(
    props: React.ImgHTMLAttributes<HTMLImageElement> & {
      fill?: boolean;
      priority?: boolean;
    },
  ) {
    const { fill: _fill, priority: _priority, ...rest } = props;
    return React.createElement("img", rest);
  },
}));

vi.mock("next/link", () => ({
  default: function MockNextLink({
    href,
    children,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
    href: string;
    children: React.ReactNode;
  }) {
    return React.createElement("a", { href, ...props }, children);
  },
}));

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });

  Object.defineProperty(window, "scrollTo", {
    writable: true,
    value: vi.fn(),
  });

  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: vi.fn().mockResolvedValue(undefined),
    },
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
