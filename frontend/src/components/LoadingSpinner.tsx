import React from "react";
import { Loader2 } from "lucide-react";

export interface LoadingSpinnerProps {
  size?: "small" | "medium" | "large";
  message?: string;
}

const sizeMap: Record<NonNullable<LoadingSpinnerProps["size"]>, number> = {
  small: 16,
  medium: 24,
  large: 32,
};

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ size = "medium", message }) => {
  const iconSize = sizeMap[size];
  return (
    <div className="loading-spinner" role="status" aria-live="polite">
      <Loader2 className="loading-spinner__icon" size={iconSize} />
      {message && <span className="loading-spinner__message">{message}</span>}
    </div>
  );
};
