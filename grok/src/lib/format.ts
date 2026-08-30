export function formatCnDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const datePart = iso.slice(0, 10);
  const pieces = datePart.split("-").map(Number);
  if (pieces.length < 3 || pieces.some((n) => Number.isNaN(n))) return iso;
  const [y, m, d] = pieces;
  return `${y}年${m}月${d}日`;
}

export function formatCnDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const weeks = ["日", "一", "二", "三", "四", "五", "六"];
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 周${weeks[d.getDay()]} ${hh}:${mm}`;
}

export function formatTodayHeader(date = new Date()): string {
  const weeks = ["日", "一", "二", "三", "四", "五", "六"];
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 周${weeks[date.getDay()]}`;
}

export function compactUrl(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname.length > 28 ? `${u.pathname.slice(0, 28)}…` : u.pathname;
    return `${u.host}${path}`;
  } catch {
    return url.length > 36 ? `${url.slice(0, 36)}…` : url;
  }
}

export function clampText(text: string, max = 72): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}
