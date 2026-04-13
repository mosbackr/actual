import { Suspense } from "react";
import InsightsDashboard from "./insights-dashboard";

export default function InsightsPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-7xl mx-auto">
          <div className="mb-6">
            <h1 className="font-serif text-3xl text-text-primary">Insights</h1>
            <p className="text-text-secondary mt-1">
              Explore deal flow, scores, and funding across the platform.
            </p>
          </div>
          <div className="text-center py-20 text-text-tertiary text-sm">Loading insights...</div>
        </div>
      }
    >
      <InsightsDashboard />
    </Suspense>
  );
}
