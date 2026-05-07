export function $(id) {
  return document.getElementById(id);
}

export function safeNum(value, digits = 0) {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return "0";
  }
  return num.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function pct(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return "0.0%";
  }
  return `${(num * 100).toFixed(1)}%`;
}

export function iso(value) {
  if (!value) {
    return "-";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

export function showFlash(message, kind = "ok") {
  const flash = $("flash");
  if (!flash) {
    return;
  }
  flash.textContent = message;
  flash.className = `flash ${kind} show`;
  window.setTimeout(() => {
    flash.className = "flash";
  }, 2600);
}

export function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export async function api(path, options = {}) {
  const init = {
    method: options.method || "GET",
    headers: {},
    credentials: "same-origin",
  };

  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  const response = await fetch(path, init);
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const code =
      payload && payload.detail && payload.detail.code
        ? payload.detail.code
        : `HTTP_${response.status}`;
    if (response.status === 403) {
      window.location.assign("/ops/login");
    }
    throw new Error(code);
  }

  return payload;
}

export function renderCards(target, cards) {
  if (!target) {
    return;
  }
  target.innerHTML = "";
  cards.forEach((card) => {
    const article = document.createElement("article");
    article.className = "card";

    const label = document.createElement("p");
    label.className = "label";
    label.textContent = card.label;

    const value = document.createElement("p");
    value.className = "value";
    value.textContent = card.value;

    article.append(label, value);
    target.appendChild(article);
  });
}

export function createActionButton({ label, className, onClick }) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `tiny ${className || "ghost"}`;
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

export function renderJson(target, payload) {
  if (!target) {
    return;
  }
  target.textContent = JSON.stringify(payload, null, 2);
}
