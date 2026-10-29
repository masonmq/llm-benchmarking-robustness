window.apiFetch = function (path, options = {}) {
  const base = (window.APP_CONFIG.apiBase || "").replace(/\/$/, "");
  const headers = new Headers(options.headers || {});
  const token = localStorage.getItem("annotation-token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const separator = String(path).includes("?") ? "&" : "?";
  const paper = window.APP_CONFIG.paperId ? `${separator}paper=${encodeURIComponent(window.APP_CONFIG.paperId)}` : "";
  return fetch(base + path + paper, {...options, headers, credentials: base ? "omit" : "include"});
};
