import React, { useMemo, useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Copy, FileText } from "lucide-react";

const STATUS_STYLES: Record<
  string,
  { label: string; background: string; color: string; icon: React.ComponentType<{ size?: number }> }
> = {
  success: {
    label: "Success",
    background: "#dcfce7",
    color: "#166534",
    icon: CheckCircle2,
  },
  no_findings: {
    label: "No Findings",
    background: "#e2e8f0",
    color: "#334155",
    icon: FileText,
  },
  requires_review: {
    label: "Requires Review",
    background: "#fef3c7",
    color: "#92400e",
    icon: AlertTriangle,
  },
  error: {
    label: "Error",
    background: "#fee2e2",
    color: "#b91c1c",
    icon: AlertCircle,
  },
};

const MAX_PREVIEW_CHARS = 800;

export interface ReportViewerProps {
  reportText: string;
  status: string;
  processingTimeMs?: number;
  sessionId?: string;
  message?: string;
}

export const ReportViewer: React.FC<ReportViewerProps> = ({
  reportText,
  status,
  processingTimeMs,
  sessionId,
  message,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const statusStyle = STATUS_STYLES[status] ?? STATUS_STYLES.error;

  const shouldTruncate = reportText.length > MAX_PREVIEW_CHARS;
  const displayText = useMemo(() => {
    if (expanded || !shouldTruncate) {
      return reportText;
    }
    return `${reportText.slice(0, MAX_PREVIEW_CHARS)}...`;
  }, [expanded, reportText, shouldTruncate]);

  const handleToggle = () => setExpanded((prev) => !prev);

  const handleCopySession = async () => {
    if (!sessionId) {
      return;
    }
    try {
      await navigator.clipboard.writeText(sessionId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section
      style={{
        backgroundColor: "#ffffff",
        borderRadius: "16px",
        border: "1px solid #e2e8f0",
        padding: "24px",
        boxShadow: "0 10px 30px rgba(15, 23, 42, 0.08)",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
      }}
    >
      <header style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "6px 16px",
              borderRadius: "999px",
              backgroundColor: statusStyle.background,
              color: statusStyle.color,
              fontWeight: 600,
              fontSize: "0.95rem",
              textTransform: "uppercase",
              letterSpacing: "0.02em",
            }}
          >
            {React.createElement(statusStyle.icon, { size: 18 })}
            {statusStyle.label}
          </span>
          {processingTimeMs !== undefined && (
            <span style={{ color: "#64748b", fontSize: "0.9rem" }}>
              Processing time: {Math.round(processingTimeMs)} ms
            </span>
          )}
        </div>
        {message && (
          <p style={{ margin: 0, color: "#475569", fontSize: "0.95rem", lineHeight: 1.5 }}>
            {message}
          </p>
        )}
        {sessionId && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              backgroundColor: "#f8fafc",
              borderRadius: "12px",
              padding: "10px 14px",
            }}
          >
            <span style={{ color: "#64748b", fontSize: "0.85rem", letterSpacing: "0.01em" }}>
              Session ID: <strong style={{ color: "#1e293b" }}>{sessionId}</strong>
            </span>
            <button
              type="button"
              onClick={handleCopySession}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 12px",
                borderRadius: "8px",
                border: "1px solid #cbd5f5",
                backgroundColor: "#e0e7ff",
                color: "#312e81",
                fontSize: "0.85rem",
                fontWeight: 600,
                cursor: "pointer",
                transition: "background-color 0.2s ease",
              }}
            >
              <Copy size={16} />
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        )}
      </header>
      <div
        style={{
          backgroundColor: "#0f172a",
          borderRadius: "12px",
          padding: "20px",
          color: "#e2e8f0",
          fontFamily: "'Fira Code', 'Source Code Pro', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
          fontSize: "0.92rem",
          lineHeight: 1.6,
          position: "relative",
          minHeight: "140px",
          boxShadow: "inset 0 0 0 1px rgba(148, 163, 184, 0.2)",
        }}
      >
        <pre
          style={{
            margin: 0,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {displayText}
        </pre>
        {shouldTruncate && (
          <div style={{ marginTop: "18px" }}>
            <button
              type="button"
              onClick={handleToggle}
              style={{
                background: "none",
                border: "none",
                color: "#cbd5f5",
                fontWeight: 600,
                cursor: "pointer",
                fontSize: "0.9rem",
                textDecoration: "underline",
              }}
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          </div>
        )}
      </div>
    </section>
  );
};
