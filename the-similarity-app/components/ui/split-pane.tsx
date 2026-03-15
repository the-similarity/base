"use client";
import { useRef, useCallback, useState, useEffect, type ReactNode } from "react";

interface SplitPaneProps {
  direction: "horizontal" | "vertical";
  defaultRatio?: number;
  minRatio?: number;
  maxRatio?: number;
  first: ReactNode;
  second: ReactNode;
  className?: string;
}

export function SplitPane({
  direction,
  defaultRatio = 0.6,
  minRatio = 0.15,
  maxRatio = 0.85,
  first,
  second,
  className,
}: SplitPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(defaultRatio);
  const dragging = useRef(false);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      dragging.current = true;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      document.body.style.cursor =
        direction === "horizontal" ? "col-resize" : "row-resize";
      document.body.style.userSelect = "none";
    },
    [direction],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      let newRatio: number;
      if (direction === "horizontal") {
        newRatio = (e.clientX - rect.left) / rect.width;
      } else {
        newRatio = (e.clientY - rect.top) / rect.height;
      }
      setRatio(Math.min(maxRatio, Math.max(minRatio, newRatio)));
    },
    [direction, minRatio, maxRatio],
  );

  const handlePointerUp = useCallback(() => {
    dragging.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  // Reset on double-click
  const handleDoubleClick = useCallback(() => {
    setRatio(defaultRatio);
  }, [defaultRatio]);

  const isH = direction === "horizontal";
  const firstStyle = isH
    ? { width: `${ratio * 100}%`, height: "100%" }
    : { height: `${ratio * 100}%`, width: "100%" };
  const secondStyle = isH
    ? { width: `${(1 - ratio) * 100}%`, height: "100%" }
    : { height: `${(1 - ratio) * 100}%`, width: "100%" };

  return (
    <div
      ref={containerRef}
      className={`split-pane split-pane--${direction} ${className ?? ""}`}
    >
      <div className="split-pane__panel" style={firstStyle}>
        {first}
      </div>
      <div
        className={`split-pane__divider split-pane__divider--${direction}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onDoubleClick={handleDoubleClick}
        role="separator"
        aria-orientation={isH ? "vertical" : "horizontal"}
        tabIndex={0}
      >
        <div className="split-pane__divider-handle" />
      </div>
      <div className="split-pane__panel" style={secondStyle}>
        {second}
      </div>
    </div>
  );
}
