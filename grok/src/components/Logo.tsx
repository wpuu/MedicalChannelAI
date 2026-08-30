export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="8" fill="#1B4D3E" />
      <path
        d="M16 7.5v17M9.5 12.5h13"
        stroke="#F4EFE4"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <path
        d="M10 21.5h12"
        stroke="#C9D7D1"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}
