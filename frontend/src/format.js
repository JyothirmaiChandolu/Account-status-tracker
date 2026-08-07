export function formatDateIST(iso) {
  if (!iso) return "Never";
  const d = new Date(iso);
  const formatted = d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${formatted} IST`;
}
