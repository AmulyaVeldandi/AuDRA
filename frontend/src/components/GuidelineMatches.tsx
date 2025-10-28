import React from "react";
import type { Recommendation } from "../api/client";
import { GuidelineMatch } from "./GuidelineMatch";

export interface GuidelineMatchesProps {
  recommendations: Recommendation[];
}

export const GuidelineMatches: React.FC<GuidelineMatchesProps> = ({ recommendations }) => {
  if (!recommendations.length) {
    return (
      <section className="card empty-state">
        <h3>No guideline matches</h3>
        <p className="text-muted">Detected findings did not map to known follow-up recommendations.</p>
      </section>
    );
  }

  return (
    <section className="guideline-matches">
      {recommendations.map((recommendation) => (
        <GuidelineMatch key={recommendation.recommendation_id} recommendation={recommendation} />
      ))}
    </section>
  );
};
