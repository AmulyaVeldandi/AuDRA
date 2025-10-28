import React from "react";
import { AlertTriangle } from "lucide-react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("AuDRA-Rad frontend encountered a rendering error:", error, errorInfo);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: undefined });
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="error-boundary">
        <AlertTriangle size={42} aria-hidden="true" />
        <h1>Something went wrong.</h1>
        <p>
          We ran into an unexpected issue while rendering the dashboard. Please try reloading the page. If the problem
          persists, open an issue on{" "}
          <a href="https://github.com/veldana/audra-rad" target="_blank" rel="noreferrer">
            GitHub
          </a>
          .
        </p>
        {import.meta.env.DEV && this.state.error && (
          <pre className="error-details">{this.state.error.message}</pre>
        )}
        <button type="button" className="primary-button" onClick={this.handleReload}>
          Try again
        </button>
      </div>
    );
  }
}
