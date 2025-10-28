import React from "react";
import { Circle } from "lucide-react";

export interface Finding {
  finding_id: string;
  type: string;
  size_mm?: number;
  location: string;
  characteristics: string[];
  confidence: number;
}

export interface FindingsListProps {
  findings: Finding[];
}

const confidenceColors: Record<"high" | "medium" | "low", string> = {
  high: "#16a34a",
  medium: "#d97706",
  low: "#dc2626",
};

const getConfidenceLevel = (confidence: number): "high" | "medium" | "low" => {
  if (confidence >= 0.75) {
    return "high";
  }
  if (confidence >= 0.4) {
    return "medium";
  }
  return "low";
};

export const FindingsList: React.FC<FindingsListProps> = ({ findings }) => {
  if (!findings.length) {
    return (
      <section
        style={{
          backgroundColor: "#ffffff",
          borderRadius: "16px",
          border: "1px solid #e2e8f0",
          padding: "24px",
          textAlign: "center",
          color: "#94a3b8",
        }}
      >
        No findings detected.
      </section>
    );
  }

  return (
    <section
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "16px",
      }}
    >
      {findings.map((finding) => {
        const level = getConfidenceLevel(finding.confidence);
        const confidencePercentage = Math.round(finding.confidence * 100);

        return (
          <article
            key={finding.finding_id}
            style={{
              backgroundColor: "#ffffff",
              borderRadius: "18px",
              border: "1px solid #e2e8f0",
              padding: "20px",
              boxShadow: "0 12px 32px rgba(15, 23, 42, 0.08)",
              display: "grid",
              gap: "12px",
            }}
          >
            <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h3
                  style={{
                    margin: 0,
                    color: "#0f172a",
                    fontSize: "1.1rem",
                    fontWeight: 700,
                    textTransform: "capitalize",
                  }}
                >
                  {finding.type.replace(/_/g, " ")}
                </h3>
                <span style={{ color: "#64748b", fontSize: "0.9rem" }}>{finding.location}</span>
              </div>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "6px 14px",
                  borderRadius: "999px",
                  color: confidenceColors[level],
                  backgroundColor: `${confidenceColors[level]}20`,
                  fontWeight: 600,
                  fontSize: "0.85rem",
                  letterSpacing: "0.02em",
                }}
              >
                <Circle size={14} fill={confidenceColors[level]} color={confidenceColors[level]} />
                {confidencePercentage}% confidence
              </span>
            </header>
            <div style={{ color: "#475569", fontSize: "0.95rem", display: "flex", gap: "16px" }}>
              <div>
                <span style={{ fontWeight: 600 }}>Size:</span>{" "}
                {finding.size_mm ? `${finding.size_mm.toFixed(1)} mm` : "Not specified"}
              </div>
              <div>
                <span style={{ fontWeight: 600 }}>Location:</span> {finding.location}
              </div>
            </div>
            {finding.characteristics.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                {finding.characteristics.map((trait) => (
                  <span
                    key={trait}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "12px",
                      backgroundColor: "#eef2ff",
                      color: "#3730a3",
                      fontSize: "0.85rem",
                      fontWeight: 600,
                      textTransform: "capitalize",
                    }}
                  >
                    {trait.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            )}
          </article>
        );
      })}
    </section>
  );
};
