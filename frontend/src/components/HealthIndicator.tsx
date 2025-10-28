import React, { useMemo } from "react";
import { format } from "date-fns";

interface ServiceStatuses {
  llm: string;
  embeddings: string;
  vector_store: string;
  ehr: string;
  [key: string]: string;
}

export interface HealthStatus {
  status: "healthy" | "degraded" | "unhealthy";
  services: ServiceStatuses;
  timestamp: string;
}

export interface HealthIndicatorProps {
  healthData?: HealthStatus;
  isLoading: boolean;
}

const STATUS_LABELS: Record<HealthStatus["status"], string> = {
  healthy: "All systems operational",
  degraded: "Performance degraded",
  unhealthy: "Service outage",
};

const STATUS_CLASS: Record<HealthStatus["status"], string> = {
  healthy: "status-success",
  degraded: "status-warning",
  unhealthy: "status-error",
};

export const HealthIndicator: React.FC<HealthIndicatorProps> = ({ healthData, isLoading }) => {
  const status = healthData?.status ?? "unhealthy";
  const statusLabel = STATUS_LABELS[status];
  const statusClass = STATUS_CLASS[status];

  const formattedTimestamp = useMemo(() => {
    if (!healthData?.timestamp) {
      return null;
    }
    try {
      return format(new Date(healthData.timestamp), "MMM d, yyyy at HH:mm:ss");
    } catch {
      return healthData.timestamp;
    }
  }, [healthData?.timestamp]);

  return (
    <aside className={`health-indicator ${statusClass}`}>
      <div className="health-summary" aria-live="polite">
        <span className="health-dot" aria-hidden="true" />
        <span>{isLoading ? "Checking system health..." : statusLabel}</span>
      </div>
      {healthData && (
        <div className="health-tooltip">
          <strong>Status</strong>
          <span>{statusLabel}</span>
          <strong>Last checked</strong>
          <span>{formattedTimestamp ?? "-"}</span>
          <strong>Services</strong>
          <ul>
            {Object.entries(healthData.services).map(([service, serviceStatus]) => (
              <li key={service}>
                <span className="service-name">{service.replace(/_/g, " ")}</span>
                <span className={`service-status service-${serviceStatus}`}>{serviceStatus}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
};
