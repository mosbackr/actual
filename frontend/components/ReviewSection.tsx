"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, authHeaders } from "@/lib/api";
import type { Review } from "@/lib/types";

function scoreColor(score: number): string {
  if (score >= 70) return "text-score-high";
  if (score >= 40) return "text-score-mid";
  return "text-score-low";
}

function ReviewCard({
  review,
  canVote,
  onVote,
}: {
  review: Review;
  canVote: boolean;
  onVote: (reviewId: string, voteType: "up" | "down") => void;
}) {
  return (
    <div className="rounded border border-border bg-surface p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-text-primary text-sm">{review.user_name || "Anonymous"}</span>
            <span className="text-xs px-2 py-0.5 rounded border border-border text-text-tertiary">
              {review.review_type === "contributor" ? "Contributor" : "Community"}
            </span>
          </div>
          <p className="text-xs text-text-tertiary mt-0.5">
            {new Date(review.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className={`font-serif text-xl tabular-nums ${scoreColor(review.overall_score)}`}>
          {Math.round(review.overall_score)}
        </div>
      </div>

      {review.comment && (
        <p className="text-sm text-text-secondary mb-3">{review.comment}</p>
      )}

      {review.dimension_scores && Object.keys(review.dimension_scores).length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {Object.entries(review.dimension_scores).map(([dim, score]) => (
            <span key={dim} className="text-xs px-2 py-1 rounded bg-background text-text-tertiary">
              {dim}: <span className={`font-medium ${scoreColor(score as number)}`}>{Math.round(score as number)}</span>
            </span>
          ))}
        </div>
      )}

      {canVote && (
        <div className="flex items-center gap-3 pt-2 border-t border-border">
          <button
            onClick={() => onVote(review.id, "up")}
            className={`flex items-center gap-1 text-xs transition ${
              review.current_user_vote === "up"
                ? "text-score-high font-medium"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
            {review.upvotes}
          </button>
          <button
            onClick={() => onVote(review.id, "down")}
            className={`flex items-center gap-1 text-xs transition ${
              review.current_user_vote === "down"
                ? "text-score-low font-medium"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12l7 7 7-7" />
            </svg>
            {review.downvotes}
          </button>
        </div>
      )}
    </div>
  );
}

interface DimensionInfo {
  name: string;
  weight: number;
}

function ReviewForm({
  slug,
  dimensions,
  onSubmitted,
}: {
  slug: string;
  dimensions: DimensionInfo[];
  onSubmitted: (review: Review) => void;
}) {
  const { data: session } = useSession();
  const [comment, setComment] = useState("");
  const [dimScores, setDimScores] = useState<Record<string, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const initial: Record<string, number> = {};
    dimensions.forEach((d) => (initial[d.name] = 50));
    setDimScores(initial);
  }, [dimensions]);

  // Auto-calculate overall score as weighted average of dimension scores
  const overallScore = dimensions.length > 0
    ? Math.round(
        dimensions.reduce((sum, d) => sum + (dimScores[d.name] || 50) * d.weight, 0) /
        dimensions.reduce((sum, d) => sum + d.weight, 0)
      )
    : 50;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session) return;
    const token = (session as any).backendToken;
    if (!token) return;

    setSubmitting(true);
    setError("");
    try {
      const result = await api.createReview(token, slug, {
        overall_score: overallScore,
        dimension_scores: dimensions.length > 0 ? dimScores : undefined,
        comment: comment || undefined,
      });
      onSubmitted(result);
      setComment("");
      const reset: Record<string, number> = {};
      dimensions.forEach((d) => (reset[d.name] = 50));
      setDimScores(reset);
    } catch (err: any) {
      setError(err.message || "Failed to submit review");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="rounded border border-border bg-surface p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-text-primary">Submit Your Score</h4>
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-tertiary">Overall</span>
          <span className={`font-serif text-xl tabular-nums ${scoreColor(overallScore)}`}>{overallScore}</span>
        </div>
      </div>

      {dimensions.length > 0 ? (
        <div className="space-y-3">
          {dimensions.map((dim) => (
            <div key={dim.name}>
              <label className="flex items-center justify-between text-sm text-text-secondary mb-1">
                <span>{dim.name}</span>
                <span className={`font-medium tabular-nums ${scoreColor(dimScores[dim.name] || 50)}`}>
                  {dimScores[dim.name] || 50}
                </span>
              </label>
              <input
                type="range"
                min="0"
                max="100"
                value={dimScores[dim.name] || 50}
                onChange={(e) =>
                  setDimScores((prev) => ({ ...prev, [dim.name]: Number(e.target.value) }))
                }
                className="w-full accent-accent"
              />
            </div>
          ))}
        </div>
      ) : (
        <div>
          <label className="flex items-center justify-between text-sm text-text-secondary mb-1">
            <span>Overall Score</span>
            <span className={`font-medium tabular-nums ${scoreColor(overallScore)}`}>{overallScore}</span>
          </label>
          <input
            type="range"
            min="0"
            max="100"
            value={50}
            onChange={() => {}}
            className="w-full accent-accent"
          />
        </div>
      )}

      <div>
        <label className="block text-sm text-text-secondary mb-1">Comment (optional)</label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          placeholder="Share your analysis..."
          className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-text-primary placeholder-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent outline-none"
        />
      </div>

      {error && <p className="text-score-low text-xs">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50 transition"
      >
        {submitting ? "Submitting..." : "Submit Review"}
      </button>
    </form>
  );
}

export function ReviewSection({
  slug,
  dimensions,
}: {
  slug: string;
  dimensions: DimensionInfo[];
}) {
  const { data: session } = useSession();
  const [activeTab, setActiveTab] = useState<"contributor" | "community">("contributor");
  const [contributorReviews, setContributorReviews] = useState<Review[]>([]);
  const [communityReviews, setCommunityReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasReviewedContributor, setHasReviewedContributor] = useState(false);
  const [hasReviewedCommunity, setHasReviewedCommunity] = useState(false);

  const isContributor =
    session && ((session as any).role === "expert" || (session as any).role === "superadmin");

  useEffect(() => {
    loadReviews();
  }, [session]);

  async function loadReviews() {
    setLoading(true);
    const token = session ? (session as any).backendToken : undefined;
    try {
      const [contrib, community] = await Promise.all([
        api.getReviews(slug, "contributor", token),
        api.getReviews(slug, "community", token),
      ]);
      setContributorReviews(contrib);
      setCommunityReviews(community);

      if (session) {
        const userId = (session as any).backendUserId;
        setHasReviewedContributor(contrib.some((r) => r.user_id === userId));
        setHasReviewedCommunity(community.some((r) => r.user_id === userId));
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }

  async function handleVote(reviewId: string, voteType: "up" | "down") {
    if (!session) return;
    const token = (session as any).backendToken;
    if (!token) return;

    try {
      const updated = await api.voteOnReview(token, reviewId, voteType);
      // Update in the correct list
      setContributorReviews((prev) =>
        prev.map((r) => (r.id === updated.id ? updated : r))
      );
      setCommunityReviews((prev) =>
        prev.map((r) => (r.id === updated.id ? updated : r))
      );
    } catch {
      // silently fail
    }
  }

  function handleNewReview(review: Review) {
    if (review.review_type === "contributor") {
      setContributorReviews((prev) => [review, ...prev]);
      setHasReviewedContributor(true);
    } else {
      setCommunityReviews((prev) => [review, ...prev]);
      setHasReviewedCommunity(true);
    }
  }

  const activeReviews = activeTab === "contributor" ? contributorReviews : communityReviews;

  // Can write: contributors write contributor reviews, users write community reviews
  const canWrite =
    session &&
    ((activeTab === "contributor" && isContributor && !hasReviewedContributor) ||
      (activeTab === "community" && !isContributor && !hasReviewedCommunity));

  // Can vote: contributors on contributor reviews, users on community reviews
  const canVote =
    !!session &&
    ((activeTab === "contributor" && !!isContributor) ||
      (activeTab === "community" && !isContributor));

  return (
    <section className="mb-12">
      <h2 className="font-serif text-xl text-text-primary mb-4">Reviews & Scoring</h2>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-6 border-b border-border">
        <button
          onClick={() => setActiveTab("contributor")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
            activeTab === "contributor"
              ? "border-accent text-accent"
              : "border-transparent text-text-tertiary hover:text-text-secondary"
          }`}
        >
          Contributor ({contributorReviews.length})
        </button>
        <button
          onClick={() => setActiveTab("community")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
            activeTab === "community"
              ? "border-accent text-accent"
              : "border-transparent text-text-tertiary hover:text-text-secondary"
          }`}
        >
          Community ({communityReviews.length})
        </button>
      </div>

      {loading ? (
        <p className="text-text-tertiary text-sm">Loading reviews...</p>
      ) : (
        <div className="space-y-4">
          {/* Review form */}
          {canWrite && (
            <ReviewForm slug={slug} dimensions={dimensions} onSubmitted={handleNewReview} />
          )}

          {!session && (
            <div className="rounded border border-border bg-surface p-5 text-center">
              <p className="text-sm text-text-secondary mb-3">Sign in to score and review this company.</p>
              <Link
                href="/auth/signin"
                className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover transition"
              >
                Sign In
              </Link>
            </div>
          )}

          {session && !canWrite && activeTab === "contributor" && !isContributor && (
            <div className="rounded border border-border bg-surface p-4">
              <p className="text-xs text-text-tertiary">
                Only approved contributors can submit contributor reviews.{" "}
                <Link href="/experts/apply" className="text-accent hover:text-accent-hover transition">
                  Apply to become a contributor &rarr;
                </Link>
              </p>
            </div>
          )}

          {/* Reviews list */}
          {activeReviews.length === 0 ? (
            <p className="text-text-tertiary text-sm py-4 text-center">
              No {activeTab} reviews yet.
            </p>
          ) : (
            activeReviews.map((review) => (
              <ReviewCard
                key={review.id}
                review={review}
                canVote={canVote}
                onVote={handleVote}
              />
            ))
          )}
        </div>
      )}
    </section>
  );
}
