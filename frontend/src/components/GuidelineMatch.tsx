import React, { useState } from "react";
import { AlertTriangle, Calendar, ChevronDown, ChevronUp, FileText } from "lucide-react";
import type { Recommendation, UrgencyLevel } from "../api/client";

export interface GuidelineMatchProps {
  recommendation: Recommendation;
  findingType?: string;
}

const URGENCY_STYLES: Record<UrgencyLevel, { label: string; background: string; color: string }> = {
  routine: {
    label: "Routine",
    background: "#e2e8f0",
    color: "#1f2937",
  },
  priority: {
    label: "Priority",
    background: "#fef3c7",
    color: "#92400e",
  },
  urgent: {
    label: "Urgent",
    background: "#fee2e2",
    color: "#b91c1c",
  },
  stat: {
    label: "STAT",
    background: "rgba(248, 113, 113, 0.18)",
    color: "#991b1b",
  },
};

export const GuidelineMatch: React.FC<GuidelineMatchProps> = ({ recommendation, findingType }) => {
  const [expanded, setExpanded] = useState(false);
  const urgencyStyle = URGENCY_STYLES[recommendation.urgency];
  const timeframeLabel = recommendation.timeframe_months
    ? `${recommendation.timeframe_months} month${recommendation.timeframe_months === 1 ? "" : "s"}`
    : "No timeframe specified";
  const confidencePercentage = Math.round(recommendation.confidence * 100);

  return (
    <article
      style={{
        backgroundColor: "#ffffff",
        borderRadius: "20px",
        border: "1px solid #e2e8f0",
        padding: "24px",
        boxShadow: "0 16px 40px rgba(15, 23, 42, 0.08)",
        display: "flex",
        flexDirection: "column",
        gap: "18px",
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {findingType && (
            <span style={{ color: "#94a3b8", fontSize: "0.85rem", letterSpacing: "0.08em" }}>
              Finding: {findingType.replace(/_/g, " ")}
            </span>
          )}
          <h3 style={{ margin: 0, color: "#0f172a", fontSize: "1.2rem" }}>{recommendation.follow_up_type}</h3>
          <div style={{ color: "#475569", fontSize: "0.95rem", display: "flex", gap: "14px" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
              <Calendar size={18} />
              {timeframeLabel}
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
              <FileText size={18} />
              Confidence: {confidencePercentage}%
            </span>
          </div>
        </div>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "8px 16px",
            borderRadius: "999px",
            backgroundColor: urgencyStyle.background,
            color: urgencyStyle.color,
            fontWeight: 700,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            fontSize: "0.8rem",
          }}
        >
          <AlertTriangle size={16} />
          {urgencyStyle.label}
        </span>
      </header>
      <section
        style={{
          backgroundColor: "#f8fafc",
          borderRadius: "16px",
          border: "1px solid #e2e8f0",
          padding: "16px 20px",
        }}
      >
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            width: "100%",
            background: "none",
            border: "none",
            color: "#0f172a",
            cursor: "pointer",
            fontWeight: 600,
            fontSize: "0.95rem",
            padding: 0,
          }}
        >
          Clinical reasoning
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>
        {expanded && (
          <p style={{ marginTop: "12px", color: "#475569", lineHeight: 1.6 }}>{recommendation.reasoning}</p>
        )}
      </section>
      <footer style={{ fontStyle: "italic", color: "#64748b", fontSize: "0.85rem" }}>
        Citation: {recommendation.citation}
      </footer>
    </article>
  );
};
