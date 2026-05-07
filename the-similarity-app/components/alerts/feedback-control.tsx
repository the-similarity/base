"use client";

import { useState } from "react";
import { submitFeedback } from "../setup/setup-scanner-client";
import type { FeedbackPayload, FeedbackTargetType } from "../setup/types";
import styles from "./feedback-control.module.css";

type FeedbackControlProps = {
  targetType: FeedbackTargetType;
  targetId: string;
  compact?: boolean;
};

export function FeedbackControl({
  targetType,
  targetId,
  compact = false,
}: FeedbackControlProps) {
  const [value, setValue] = useState<FeedbackPayload["value"] | null>(null);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);

  async function save(next: FeedbackPayload["value"], nextNote = note): Promise<void> {
    setValue(next);
    await submitFeedback({
      targetType,
      targetId,
      value: next,
      note: nextNote.trim() || undefined,
    });
    setSaved(true);
  }

  return (
    <div className={styles.feedback} onClick={e => e.stopPropagation()}>
      <div className={styles.buttons} aria-label={`${targetType} feedback`}>
        <button
          type="button"
          className={styles.button}
          data-active={value === "up" ? "true" : undefined}
          aria-pressed={value === "up"}
          aria-label={`Mark ${targetType} useful`}
          title="Useful"
          onClick={() => void save("up")}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M5.8 6.8 8.4 2c.2-.4.8-.5 1.1-.2.7.6.8 1.7.4 2.6l-.7 1.5h3.5c.9 0 1.6.8 1.4 1.7l-.8 4.3c-.1.7-.7 1.2-1.4 1.2H5.8V6.8ZM2.3 6.8h2v6.3h-2V6.8Z" fill="currentColor" />
          </svg>
        </button>
        <button
          type="button"
          className={styles.button}
          data-active={value === "down" ? "true" : undefined}
          aria-pressed={value === "down"}
          aria-label={`Mark ${targetType} not useful`}
          title="Not useful"
          onClick={() => void save("down")}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M10.2 9.2 7.6 14c-.2.4-.8.5-1.1.2-.7-.6-.8-1.7-.4-2.6l.7-1.5H3.3c-.9 0-1.6-.8-1.4-1.7l.8-4.3c.1-.7.7-1.2 1.4-1.2h6.1v6.3Zm3.5 0h-2V2.9h2v6.3Z" fill="currentColor" />
          </svg>
        </button>
      </div>
      {!compact && (
        <textarea
          className={styles.note}
          value={note}
          placeholder="Optional note"
          rows={2}
          onChange={e => setNote(e.target.value)}
          onBlur={() => {
            if (value) void save(value, note);
          }}
        />
      )}
      <div className={styles.status} aria-live="polite">
        {saved ? "Feedback saved" : ""}
      </div>
    </div>
  );
}

