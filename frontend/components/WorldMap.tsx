"use client";

import { memo, useState, useCallback } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
} from "react-simple-maps";
import type { RegionMetrics } from "@/lib/types";

const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

// Map world-atlas numeric IDs to ISO 2-letter country codes
const ID_TO_ISO2: Record<string, string> = {
  "4": "AF", "8": "AL", "12": "DZ", "24": "AO", "32": "AR", "36": "AU",
  "40": "AT", "50": "BD", "56": "BE", "76": "BR", "100": "BG", "104": "MM",
  "116": "KH", "120": "CM", "124": "CA", "140": "CF", "144": "LK", "148": "TD",
  "152": "CL", "156": "CN", "170": "CO", "178": "CG", "180": "CD", "188": "CR",
  "191": "HR", "192": "CU", "196": "CY", "203": "CZ", "208": "DK", "214": "DO",
  "218": "EC", "818": "EG", "222": "SV", "226": "GQ", "231": "ET", "233": "EE",
  "246": "FI", "250": "FR", "266": "GA", "270": "GM", "268": "GE", "276": "DE",
  "288": "GH", "300": "GR", "320": "GT", "324": "GN", "328": "GY", "332": "HT",
  "340": "HN", "348": "HU", "352": "IS", "356": "IN", "360": "ID", "364": "IR",
  "368": "IQ", "372": "IE", "376": "IL", "380": "IT", "384": "CI", "388": "JM",
  "392": "JP", "400": "JO", "398": "KZ", "404": "KE", "408": "KP", "410": "KR",
  "414": "KW", "417": "KG", "418": "LA", "422": "LB", "426": "LS", "430": "LR",
  "434": "LY", "440": "LT", "442": "LU", "450": "MG", "454": "MW", "458": "MY",
  "466": "ML", "478": "MR", "484": "MX", "496": "MN", "504": "MA", "508": "MZ",
  "512": "OM", "516": "NA", "524": "NP", "528": "NL", "554": "NZ", "558": "NI",
  "562": "NE", "566": "NG", "578": "NO", "586": "PK", "591": "PA", "598": "PG",
  "600": "PY", "604": "PE", "608": "PH", "616": "PL", "620": "PT", "630": "PR",
  "634": "QA", "642": "RO", "643": "RU", "646": "RW", "682": "SA", "686": "SN",
  "688": "RS", "694": "SL", "702": "SG", "703": "SK", "704": "VN", "705": "SI",
  "706": "SO", "710": "ZA", "716": "ZW", "724": "ES", "736": "SD", "740": "SR",
  "748": "SZ", "752": "SE", "756": "CH", "760": "SY", "762": "TJ", "764": "TH",
  "768": "TG", "780": "TT", "784": "AE", "788": "TN", "792": "TR", "795": "TM",
  "800": "UG", "804": "UA", "826": "GB", "834": "TZ", "840": "US", "858": "UY",
  "860": "UZ", "862": "VE", "887": "YE", "894": "ZM", "729": "SD",
  "728": "SS", "499": "ME", "807": "MK", "70": "BA",
};

// Also handle "UK" → "GB" since our DB may store "UK"
const NORMALIZE_CODE: Record<string, string> = { UK: "GB" };

// Display names for ISO 2 codes
const CODE_TO_NAME: Record<string, string> = {
  AF: "Afghanistan", AL: "Albania", DZ: "Algeria", AO: "Angola", AR: "Argentina",
  AU: "Australia", AT: "Austria", BD: "Bangladesh", BE: "Belgium", BR: "Brazil",
  BG: "Bulgaria", MM: "Myanmar", KH: "Cambodia", CM: "Cameroon", CA: "Canada",
  CF: "Central African Rep.", LK: "Sri Lanka", TD: "Chad", CL: "Chile", CN: "China",
  CO: "Colombia", CG: "Congo", CD: "DR Congo", CR: "Costa Rica", HR: "Croatia",
  CU: "Cuba", CY: "Cyprus", CZ: "Czechia", DK: "Denmark", DO: "Dominican Rep.",
  EC: "Ecuador", EG: "Egypt", SV: "El Salvador", EE: "Estonia", ET: "Ethiopia",
  FI: "Finland", FR: "France", GA: "Gabon", GE: "Georgia", DE: "Germany",
  GH: "Ghana", GR: "Greece", GT: "Guatemala", GN: "Guinea", HT: "Haiti",
  HN: "Honduras", HU: "Hungary", IS: "Iceland", IN: "India", ID: "Indonesia",
  IR: "Iran", IQ: "Iraq", IE: "Ireland", IL: "Israel", IT: "Italy", CI: "Ivory Coast",
  JM: "Jamaica", JP: "Japan", JO: "Jordan", KZ: "Kazakhstan", KE: "Kenya",
  KP: "North Korea", KR: "South Korea", KW: "Kuwait", KG: "Kyrgyzstan",
  LA: "Laos", LB: "Lebanon", LT: "Lithuania", LU: "Luxembourg", MG: "Madagascar",
  MY: "Malaysia", MX: "Mexico", MN: "Mongolia", MA: "Morocco", MZ: "Mozambique",
  NA: "Namibia", NP: "Nepal", NL: "Netherlands", NZ: "New Zealand", NI: "Nicaragua",
  NE: "Niger", NG: "Nigeria", NO: "Norway", PK: "Pakistan", PA: "Panama",
  PG: "Papua New Guinea", PY: "Paraguay", PE: "Peru", PH: "Philippines",
  PL: "Poland", PT: "Portugal", QA: "Qatar", RO: "Romania", RU: "Russia",
  SA: "Saudi Arabia", SN: "Senegal", RS: "Serbia", SG: "Singapore", SK: "Slovakia",
  SI: "Slovenia", SO: "Somalia", ZA: "South Africa", ES: "Spain", SD: "Sudan",
  SE: "Sweden", CH: "Switzerland", SY: "Syria", TH: "Thailand", TN: "Tunisia",
  TR: "Turkey", UA: "Ukraine", AE: "UAE", GB: "United Kingdom", TZ: "Tanzania",
  US: "United States", UY: "Uruguay", UZ: "Uzbekistan", VE: "Venezuela",
  VN: "Vietnam", YE: "Yemen", ZM: "Zambia", ZW: "Zimbabwe", SS: "South Sudan",
  ME: "Montenegro", MK: "North Macedonia", BA: "Bosnia", TT: "Trinidad & Tobago",
  PR: "Puerto Rico",
};

function scoreToColor(score: number | null, max: number): string {
  if (score === null || max === 0) return "#E8E6E3";
  const t = Math.min(score / max, 1);
  const r = Math.round(232 + (184 - 232) * t);
  const g = Math.round(230 + (85 - 230) * t);
  const b = Math.round(227 + (58 - 227) * t);
  return `rgb(${r},${g},${b})`;
}

interface WorldMapProps {
  regions: RegionMetrics[];
  metric: "avg_ai_score" | "avg_expert_score" | "avg_user_score";
  selectedRegion: string | null;
  onSelectRegion: (region: string | null) => void;
}

interface TooltipData {
  name: string;
  count: number;
  avg_ai_score: number | null;
  avg_expert_score: number | null;
  avg_user_score: number | null;
  x: number;
  y: number;
}

function WorldMapInner({ regions, metric, selectedRegion, onSelectRegion }: WorldMapProps) {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  // Build lookup: normalized ISO2 → region data
  const regionMap = new Map<string, RegionMetrics>();
  for (const r of regions) {
    const code = NORMALIZE_CODE[r.region] || r.region;
    regionMap.set(code, r);
  }

  const scores = regions.map((r) => r[metric]).filter((s): s is number => s !== null);
  const maxScore = scores.length > 0 ? Math.max(...scores) : 100;

  const handleMouseMove = useCallback((geo: { id: string }, e: React.MouseEvent) => {
    const iso2 = ID_TO_ISO2[geo.id];
    if (!iso2) return;
    const data = regionMap.get(iso2);
    const name = CODE_TO_NAME[iso2] || iso2;
    setTooltip({
      name,
      count: data?.count ?? 0,
      avg_ai_score: data?.avg_ai_score ?? null,
      avg_expert_score: data?.avg_expert_score ?? null,
      avg_user_score: data?.avg_user_score ?? null,
      x: e.clientX,
      y: e.clientY,
    });
  }, [regionMap]);

  const handleMouseLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  return (
    <div className="relative">
      <ComposableMap
        projection="geoEqualEarth"
        width={900}
        height={420}
        projectionConfig={{ scale: 150, center: [0, 0] }}
      >
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const iso2 = ID_TO_ISO2[geo.id];
              const data = iso2 ? regionMap.get(iso2) : undefined;
              const score = data ? data[metric] : null;
              const isSelected = iso2 === (NORMALIZE_CODE[selectedRegion ?? ""] || selectedRegion);

              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  onClick={() => {
                    if (iso2) {
                      // Use the original DB code (reverse normalize)
                      const dbCode = Object.entries(NORMALIZE_CODE).find(([, v]) => v === iso2)?.[0] || iso2;
                      const matchingRegion = regions.find(r => r.region === dbCode || r.region === iso2);
                      const regionCode = matchingRegion?.region || iso2;
                      onSelectRegion(isSelected ? null : regionCode);
                    }
                  }}
                  onMouseMove={(e: React.MouseEvent) => handleMouseMove(geo, e)}
                  onMouseLeave={handleMouseLeave}
                  style={{
                    default: {
                      fill: isSelected ? "#B8553A" : scoreToColor(score, maxScore),
                      stroke: "#FFFFFF",
                      strokeWidth: 0.5,
                      outline: "none",
                    },
                    hover: {
                      fill: isSelected ? "#9C4530" : data ? "#D4A373" : "#DAD8D5",
                      stroke: "#FFFFFF",
                      strokeWidth: 0.75,
                      outline: "none",
                      cursor: data ? "pointer" : "default",
                    },
                    pressed: {
                      fill: "#9C4530",
                      stroke: "#FFFFFF",
                      strokeWidth: 0.75,
                      outline: "none",
                    },
                  }}
                />
              );
            })
          }
        </Geographies>
      </ComposableMap>

      {/* Hover tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 pointer-events-none rounded border border-border bg-surface px-3 py-2 shadow-lg"
          style={{ left: tooltip.x + 12, top: tooltip.y - 12 }}
        >
          <p className="text-sm font-medium text-text-primary">{tooltip.name}</p>
          {tooltip.count > 0 ? (
            <>
              <p className="text-xs text-text-secondary mt-0.5">
                {tooltip.count} startup{tooltip.count !== 1 ? "s" : ""}
              </p>
              <div className="grid grid-cols-3 gap-3 mt-1.5 text-xs">
                <div>
                  <span className="text-text-tertiary">AI</span>
                  <span className="ml-1 tabular-nums text-text-primary">
                    {tooltip.avg_ai_score?.toFixed(1) ?? "—"}
                  </span>
                </div>
                <div>
                  <span className="text-text-tertiary">Contrib</span>
                  <span className="ml-1 tabular-nums text-text-primary">
                    {tooltip.avg_expert_score?.toFixed(1) ?? "—"}
                  </span>
                </div>
                <div>
                  <span className="text-text-tertiary">Comm</span>
                  <span className="ml-1 tabular-nums text-text-primary">
                    {tooltip.avg_user_score?.toFixed(1) ?? "—"}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-xs text-text-tertiary mt-0.5">No data</p>
          )}
        </div>
      )}
    </div>
  );
}

export const WorldMap = memo(WorldMapInner);
