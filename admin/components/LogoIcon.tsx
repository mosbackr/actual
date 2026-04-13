export function LogoIcon({ size = 24, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={className}
    >
      <rect width="32" height="32" rx="6" fill="#B8553A" />
      <rect x="10" y="5" width="14" height="18" rx="1.5" fill="#FAFAF8" opacity="0.3" transform="rotate(6 17 14)" />
      <rect x="9" y="6" width="14" height="18" rx="1.5" fill="#FAFAF8" opacity="0.5" transform="rotate(2 16 15)" />
      <rect x="8" y="7" width="14" height="18" rx="1.5" fill="#FAFAF8" />
      <line x1="11" y1="12" x2="19" y2="12" stroke="#B8553A" strokeWidth="1.2" strokeLinecap="round" />
      <line x1="11" y1="15" x2="17" y2="15" stroke="#B8553A" strokeWidth="1.2" strokeLinecap="round" />
      <line x1="11" y1="18" x2="15" y2="18" stroke="#B8553A" strokeWidth="1.2" strokeLinecap="round" />
      <polyline points="11,22 14,20 16.5,21 19,18" fill="none" stroke="#B8553A" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
