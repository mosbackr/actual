import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Deep Thesis — Institutional-grade deal intelligence. Angel investor price.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OGImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          backgroundColor: "#FAFAF8",
          fontFamily: "Georgia, serif",
        }}
      >
        {/* Logo + Brand */}
        <div style={{ display: "flex", alignItems: "center", gap: "20px", marginBottom: "48px" }}>
          {/* Wireframe network logo */}
          <svg
            width="56"
            height="56"
            viewBox="0 0 32 32"
            fill="none"
          >
            <circle cx="16" cy="6" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
            <circle cx="6" cy="16" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
            <circle cx="26" cy="16" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
            <circle cx="10" cy="26" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
            <circle cx="22" cy="26" r="2.5" stroke="#F28C28" strokeWidth="1.5" />
            <circle cx="16" cy="16" r="3.5" stroke="#F28C28" strokeWidth="1.8" />
            <line x1="16" y1="8.5" x2="16" y2="12.5" stroke="#F28C28" strokeWidth="1.2" />
            <line x1="8.2" y1="14.5" x2="12.5" y2="15.5" stroke="#F28C28" strokeWidth="1.2" />
            <line x1="19.5" y1="15.5" x2="23.8" y2="14.5" stroke="#F28C28" strokeWidth="1.2" />
            <line x1="14.2" y1="18.8" x2="11.5" y2="23.8" stroke="#F28C28" strokeWidth="1.2" />
            <line x1="17.8" y1="18.8" x2="20.5" y2="23.8" stroke="#F28C28" strokeWidth="1.2" />
            <line x1="8" y1="18" x2="10.5" y2="23.5" stroke="#F28C28" strokeWidth="0.8" opacity="0.5" />
            <line x1="24" y1="18" x2="21.5" y2="23.5" stroke="#F28C28" strokeWidth="0.8" opacity="0.5" />
            <line x1="14.5" y1="7.5" x2="7.8" y2="14" stroke="#F28C28" strokeWidth="0.8" opacity="0.5" />
            <line x1="17.5" y1="7.5" x2="24.2" y2="14" stroke="#F28C28" strokeWidth="0.8" opacity="0.5" />
          </svg>
          <span style={{ fontSize: "42px", color: "#1A1A1A" }}>Deep Thesis</span>
        </div>

        {/* Headline */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "40px" }}>
          <span style={{ fontSize: "52px", color: "#1A1A1A", lineHeight: 1.15 }}>
            Institutional-grade deal intelligence.
          </span>
          <span style={{ fontSize: "52px", color: "#F28C28", lineHeight: 1.15 }}>
            Angel investor price.
          </span>
        </div>

        {/* Stats bar */}
        <div style={{ display: "flex", gap: "40px", marginBottom: "40px" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "28px", color: "#1A1A1A", fontFamily: "system-ui, sans-serif" }}>1,000+</span>
            <span style={{ fontSize: "14px", color: "#9B9B9B", fontFamily: "system-ui, sans-serif" }}>buy-side transactions</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "28px", color: "#1A1A1A", fontFamily: "system-ui, sans-serif" }}>2,800+</span>
            <span style={{ fontSize: "14px", color: "#9B9B9B", fontFamily: "system-ui, sans-serif" }}>companies profiled</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "28px", color: "#1A1A1A", fontFamily: "system-ui, sans-serif" }}>8</span>
            <span style={{ fontSize: "14px", color: "#9B9B9B", fontFamily: "system-ui, sans-serif" }}>AI agents per analysis</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "28px", color: "#F28C28", fontFamily: "system-ui, sans-serif" }}>$19.99</span>
            <span style={{ fontSize: "14px", color: "#9B9B9B", fontFamily: "system-ui, sans-serif" }}>/mo starter</span>
          </div>
        </div>

        {/* URL */}
        <span style={{ fontSize: "18px", color: "#6B6B6B", fontFamily: "system-ui, sans-serif" }}>
          deepthesis.co
        </span>
      </div>
    ),
    { ...size }
  );
}
