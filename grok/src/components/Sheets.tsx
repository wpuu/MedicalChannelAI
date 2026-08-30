import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

export function Sheet({
  open,
  title,
  caption,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  caption?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center">
      <button
        type="button"
        className="absolute inset-0 bg-stone-900/35"
        aria-label="关闭"
        onClick={onClose}
      />
      <div className="relative max-h-[88dvh] w-full max-w-[430px] overflow-y-auto rounded-t-2xl bg-white shadow-2xl sm:mx-4 sm:rounded-2xl">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-stone-100 bg-white px-4 py-3">
          <div className="min-w-0">
            <h3 className="text-[16px] font-semibold text-stone-900">{title}</h3>
            {caption ? (
              <p className="mt-1 text-[12px] leading-relaxed text-stone-500">{caption}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-100 text-stone-600"
            aria-label="关闭面板"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-4 pb-6 pt-3">{children}</div>
      </div>
    </div>
  );
}
