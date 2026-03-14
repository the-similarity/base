"use client";

import { Component, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  fallback?: ReactNode;
};

type State = {
  hasError: boolean;
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div style={{
          padding: "40px",
          maxWidth: "600px",
          margin: "80px auto",
          textAlign: "center",
          fontFamily: "var(--font-family, sans-serif)",
        }}>
          <h2 style={{ fontSize: "18px", fontWeight: 700, marginBottom: "12px" }}>
            Something went wrong
          </h2>
          <p style={{ fontSize: "13px", color: "#8a8a8a", marginBottom: "20px" }}>
            {this.state.error?.message ?? "An unexpected error occurred."}
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: "8px 20px",
              fontSize: "13px",
              fontWeight: 600,
              border: "1px solid #e8e8e8",
              borderRadius: "8px",
              background: "#ffffff",
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
