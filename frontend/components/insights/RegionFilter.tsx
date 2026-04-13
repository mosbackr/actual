"use client";

import { useEffect, useRef, useState } from "react";

const STATE_NAMES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa",
  KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada",
  NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma",
  OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina",
  SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont",
  VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin",
  WY: "Wyoming", DC: "District of Columbia",
};

const COUNTRY_NAMES: Record<string, string> = {
  US: "United States", GB: "United Kingdom", CA: "Canada", DE: "Germany",
  FR: "France", AU: "Australia", IN: "India", IL: "Israel", SG: "Singapore",
  BR: "Brazil", JP: "Japan", KR: "South Korea", CN: "China", SE: "Sweden",
  NL: "Netherlands", CH: "Switzerland", IE: "Ireland", ES: "Spain",
  IT: "Italy", NO: "Norway", DK: "Denmark", FI: "Finland", NZ: "New Zealand",
  AE: "UAE", SA: "Saudi Arabia", MX: "Mexico", AR: "Argentina", CL: "Chile",
  CO: "Colombia", NG: "Nigeria", KE: "Kenya", ZA: "South Africa", EG: "Egypt",
  PL: "Poland", CZ: "Czechia", RO: "Romania", UA: "Ukraine", TR: "Turkey",
  TH: "Thailand", VN: "Vietnam", PH: "Philippines", ID: "Indonesia",
  MY: "Malaysia", BD: "Bangladesh", PK: "Pakistan",
};

interface Props {
  availableCountries: string[];
  availableStates: string[];
  selectedCountries: string[];
  selectedStates: string[];
  onCountriesChange: (countries: string[]) => void;
  onStatesChange: (states: string[]) => void;
}

export function RegionFilter({
  availableCountries,
  availableStates,
  selectedCountries,
  selectedStates,
  onCountriesChange,
  onStatesChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const showStates = selectedCountries.includes("US");
  const totalSelected = selectedCountries.length + selectedStates.length;

  const toggleCountry = (code: string) => {
    if (selectedCountries.includes(code)) {
      onCountriesChange(selectedCountries.filter((c) => c !== code));
      if (code === "US") onStatesChange([]);
    } else {
      onCountriesChange([...selectedCountries, code]);
    }
  };

  const toggleState = (code: string) => {
    onStatesChange(
      selectedStates.includes(code)
        ? selectedStates.filter((s) => s !== code)
        : [...selectedStates, code]
    );
  };

  const displayText =
    totalSelected === 0
      ? "Region"
      : totalSelected <= 2
        ? [...selectedCountries.map((c) => COUNTRY_NAMES[c] || c), ...selectedStates.map((s) => STATE_NAMES[s] || s)].join(", ")
        : `${totalSelected} regions`;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 rounded border px-3 py-2 text-sm outline-none transition ${
          totalSelected > 0
            ? "border-accent bg-accent/5 text-accent"
            : "border-border bg-surface text-text-primary"
        }`}
      >
        <span className="max-w-[180px] truncate">{displayText}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-64 max-h-80 overflow-y-auto rounded border border-border bg-surface shadow-lg">
          {totalSelected > 0 && (
            <button
              onClick={() => { onCountriesChange([]); onStatesChange([]); }}
              className="w-full px-3 py-2 text-left text-xs text-accent hover:bg-hover-row transition border-b border-border"
            >
              Clear all
            </button>
          )}
          <div className="px-3 py-1.5 text-xs font-medium text-text-tertiary border-b border-border">
            Countries
          </div>
          {availableCountries.map((code) => (
            <label
              key={code}
              className="flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-hover-row cursor-pointer transition"
            >
              <input
                type="checkbox"
                checked={selectedCountries.includes(code)}
                onChange={() => toggleCountry(code)}
                className="accent-accent"
              />
              {COUNTRY_NAMES[code] || code}
            </label>
          ))}
          {showStates && availableStates.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-xs font-medium text-text-tertiary border-t border-b border-border mt-1">
                US States
              </div>
              {availableStates.map((code) => (
                <label
                  key={code}
                  className="flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-hover-row cursor-pointer transition pl-5"
                >
                  <input
                    type="checkbox"
                    checked={selectedStates.includes(code)}
                    onChange={() => toggleState(code)}
                    className="accent-accent"
                  />
                  {STATE_NAMES[code] || code}
                </label>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
