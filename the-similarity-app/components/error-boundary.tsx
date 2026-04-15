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

      // Editorial deck error card: white surface, quiet border, mono error label
      // pinned on top of the message to read like a stamped tag on a printed page.
      return (
        <div style={{
          padding: "40px",
          maxWidth: "600px",
          margin: "80px auto",
          textAlign: "center",
          fontFamily: "var(--font-sans)",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderTop: "3px solid var(--text-primary)",
          color: "var(--text-primary)",
        }}>
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            letterSpacing: "1.5px",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            marginBottom: "12px",
          }}>
            Error
          </div>
          <h2 style={{ fontSize: "20px", fontWeight: 600, marginBottom: "12px", letterSpacing: "-0.01em" }}>
            Something went wrong
          </h2>
          <p style={{ fontSize: "13px", color: "var(--text-muted)", marginBottom: "24px" }}>
            {this.state.error?.message ?? "An unexpected error occurred."}
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: "8px 20px",
              fontSize: "11px",
              fontFamily: "var(--font-mono)",
              fontWeight: 600,
              letterSpacing: "1px",
              textTransform: "uppercase",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius-sm)",
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
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
