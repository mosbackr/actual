export function LogoIcon({ size = 24, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={className}
      fill="none"
    >
      {/* Neural network nodes — representing AI/quant intelligence */}
      <circle cx="16" cy="6" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
      <circle cx="6" cy="16" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
      <circle cx="26" cy="16" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
      <circle cx="10" cy="26" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
      <circle cx="22" cy="26" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
      {/* Center node — larger, the "thesis" core */}
      <circle cx="16" cy="16" r="3.5" stroke="#F28C28" strokeWidth="1.8" />
      {/* Connections — wireframe network edges */}
      <line x1="16" y1="8.5" x2="16" y2="12.5" stroke="#F28C28" strokeWidth="1.2" />
      <line x1="8.2" y1="14.5" x2="12.5" y2="15.5" stroke="#F28C28" strokeWidth="1.2" />
      <line x1="19.5" y1="15.5" x2="23.8" y2="14.5" stroke="#F28C28" strokeWidth="1.2" />
      <line x1="14.2" y1="18.8" x2="11.5" y2="23.8" stroke="#F28C28" strokeWidth="1.2" />
      <line x1="17.8" y1="18.8" x2="20.5" y2="23.8" stroke="#F28C28" strokeWidth="1.2" />
      {/* Cross connections for depth */}
      <line x1="8" y1="18" x2="10.5" y2="23.5" stroke="#F28C28" strokeWidth="0.8" opacity="0.5" />
      <line x1="24" y1="18" x2="21.5" y2="23.5" stroke="#F28C28" strokeWidth="0.8" opacity="0.5" />
      <line x1="14.5" y1="7.5" x2="7.8" y2="14" stroke="#F28C28" strokeWidth="0.8" opacity="0.5" />
      <line x1="17.5" y1="7.5" x2="24.2" y2="14" stroke="#F28C28" strokeWidth="0.8" opacity="0.5" />
    </svg>
  );
}
