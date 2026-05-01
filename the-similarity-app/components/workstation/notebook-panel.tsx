/**
 * NotebookPanel — left-rail editable notebook entries.
 *
 * What this is for
 * ----------------
 * Replaces the previously hardcoded "Nine lenses agree…" prose paragraph
 * with a small editable list of entries the user actually writes. Each
 * entry captures the dataset + window the user was looking at when they
 * wrote it, and clicking an entry restores both — closing the
 * "observation → re-visit" half of the workstation's artifact loop.
 *
 * Persistence is delegated entirely to {@link "../../lib/notebook"} —
 * this component is a pure rendering + input surface. It owns no state
 * beyond a draft text buffer and an "expanded" flag for the show-all
 * affordance; the durable list lives in localStorage and is passed in
 * via {@link NotebookPanelProps.entries}.
 *
 * UX contract
 * -----------
 *   - Compose: textarea + small "Add" button (or Enter without Shift).
 *     Empty/whitespace text is rejected silently — no error toast,
 *     because the rejection is obvious (the textarea stays put).
 *   - Display: 5 most-recent entries by default. A "show more"
 *     toggle expands to the full list when the user has more than 5.
 *   - Restore: clicking an entry's chrome (date or text) calls
 *     {@link NotebookPanelProps.onRestore} with the entry's
 *     dataset+window so the parent workstation can rehydrate.
 *   - Delete: the small × button on each entry calls
 *     {@link NotebookPanelProps.onDelete}. We confirm-on-click rather
 *     than two-step because the delete is locally reversible
 *     (re-typing is fast; the entries are personal observations, not
 *     database rows).
 *
 * Styling
 * -------
 * Reuses the same ``side__section`` / ``side__header`` / ``saved-list``
 * / ``saved`` rail classes as the surrounding workstation so this panel
 * blends into the rail without introducing new CSS. The textarea and
 * "Add" button have no dedicated class — they inherit form styling
 * already wired in app/globals.css.
 */

"use client";

import { useState, useCallback, type KeyboardEvent } from "react";
import type { NotebookEntry } from "../../lib/notebook";

export interface NotebookPanelProps {
  /** Persisted entries, newest first. Owned by the parent. */
  entries: NotebookEntry[];
  /**
   * Called when the user submits a new entry. The parent is responsible
   * for snapshotting the current dataset + window indices and calling
   * {@link "../../lib/notebook".addEntry}.
   *
   * `text` is already trimmed by the panel before this fires.
   */
  onAdd: (text: string) => void;
  /** Called when the user clicks the × on an entry. */
  onDelete: (id: string) => void;
  /**
   * Called when the user clicks the body of an entry. The parent is
   * expected to restore the entry's dataset and window into the live
   * workstation state.
   */
  onRestore: (entry: NotebookEntry) => void;
}

/** How many entries we render before requiring "show more". */
const COLLAPSED_LIMIT = 5;

export function NotebookPanel({
  entries,
  onAdd,
  onDelete,
  onRestore,
}: NotebookPanelProps): React.ReactElement {
  const [draft, setDraft] = useState("");
  const [expanded, setExpanded] = useState(false);

  /**
   * Submit handler. Trims, rejects empty, calls onAdd, and clears the
   * draft buffer. The trim/empty-reject is duplicated here AND in
   * lib/notebook to keep both layers honest — the panel rejects on
   * input so the textarea clears immediately even if the parent
   * forgets to re-validate.
   */
  const submit = useCallback(() => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onAdd(trimmed);
    setDraft("");
  }, [draft, onAdd]);

  /**
   * Enter to submit, Shift+Enter for newline. Pattern matches every
   * chat input and most note-taking surfaces — no need to teach.
   * IME composition is detected via ``e.nativeEvent.isComposing`` to
   * avoid swallowing Enter mid-CJK-input.
   */
  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // ``isComposing`` lives on the native event (DOM KeyboardEvent),
      // not the synthetic React event. We read it via ``e.nativeEvent``
      // so an in-progress IME composition (CJK input) doesn't
      // accidentally submit when the user presses Enter to confirm a
      // candidate.
      const composing = (e.nativeEvent as { isComposing?: boolean }).isComposing;
      if (e.key === "Enter" && !e.shiftKey && !composing) {
        e.preventDefault();
        submit();
      }
    },
    [submit],
  );

  const visible = expanded ? entries : entries.slice(0, COLLAPSED_LIMIT);
  const hiddenCount = Math.max(0, entries.length - COLLAPSED_LIMIT);

  return (
    <div className="side__section">
      <div className="side__header">
        <span className="label">Notebook</span>
        <span
          className="mono"
          style={{ fontSize: 10.5, color: "var(--ink-3)" }}
        >
          {entries.length}
        </span>
      </div>

      {/*
       * Compose box. We style inline rather than via a new CSS class
       * because the rest of the rail does the same — no new selectors
       * means nothing to keep in sync with the Lumen re-skin's CSS
       * variable cascade.
       */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Note this moment…  (Enter to save)"
          aria-label="New notebook entry"
          style={{
            fontFamily: "inherit",
            fontSize: 12,
            lineHeight: 1.45,
            padding: "6px 8px",
            border: "1px solid var(--rule)",
            borderRadius: 3,
            background: "var(--bg-card)",
            color: "var(--ink)",
            resize: "vertical",
            minHeight: 36,
          }}
        />
        <button
          onClick={submit}
          disabled={!draft.trim()}
          aria-label="Save notebook entry"
          style={{
            alignSelf: "flex-end",
            fontFamily: "inherit",
            fontSize: 11,
            padding: "3px 10px",
            border: "1px solid var(--rule-strong)",
            background: draft.trim() ? "var(--accent)" : "var(--bg-card)",
            color: draft.trim() ? "var(--bg-card)" : "var(--ink-3)",
            borderRadius: 3,
            cursor: draft.trim() ? "pointer" : "not-allowed",
          }}
        >
          Save
        </button>
      </div>

      {entries.length === 0 ? (
        <div
          className="serif"
          style={{
            fontSize: 12,
            color: "var(--ink-3)",
            fontStyle: "italic",
            marginTop: 8,
          }}
        >
          No entries yet. Notes you save here travel with the dataset and
          window you wrote them against.
        </div>
      ) : (
        <div className="saved-list" style={{ marginTop: 8 }}>
          {visible.map((entry) => (
            <NotebookRow
              key={entry.id}
              entry={entry}
              onDelete={onDelete}
              onRestore={onRestore}
            />
          ))}
          {hiddenCount > 0 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              style={{
                fontFamily: "inherit",
                fontSize: 10.5,
                padding: "4px 0",
                background: "transparent",
                border: "none",
                color: "var(--ink-3)",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              {expanded
                ? "show fewer"
                : `show ${hiddenCount} more`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Single notebook row. Pulled out so the click-to-restore vs
 * click-to-delete event surfaces stay legible — clicking the body
 * restores; clicking the × deletes; the × stops propagation so the
 * row's restore handler doesn't also fire.
 */
interface NotebookRowProps {
  entry: NotebookEntry;
  onDelete: (id: string) => void;
  onRestore: (entry: NotebookEntry) => void;
}

function NotebookRow({
  entry,
  onDelete,
  onRestore,
}: NotebookRowProps): React.ReactElement {
  /**
   * Format the entry's wall-clock timestamp as ``MMM D``. The full ISO
   * string is on the title attribute so power users can hover for
   * resolution. Rationale for not showing time-of-day inline: the rail
   * is narrow; a compact date keeps the row readable.
   */
  const dateLabel = (() => {
    try {
      const d = new Date(entry.ts);
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    } catch {
      return "—";
    }
  })();

  return (
    <div
      className="saved"
      style={{ alignItems: "flex-start", gap: 6 }}
      onClick={() => onRestore(entry)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onRestore(entry);
        }
      }}
      title={`Click to restore. Saved ${entry.ts}`}
    >
      <span
        className="saved__date"
        style={{ flex: "0 0 auto", color: "var(--ink-3)" }}
      >
        {dateLabel}
      </span>
      <span
        className="saved__name"
        style={{
          flex: 1,
          whiteSpace: "normal",
          fontSize: 11.5,
          lineHeight: 1.4,
          color: "var(--ink-2)",
        }}
      >
        {entry.text}
      </span>
      <button
        aria-label="Delete entry"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(entry.id);
        }}
        style={{
          flex: "0 0 auto",
          background: "transparent",
          border: "none",
          color: "var(--ink-3)",
          fontSize: 12,
          padding: "0 2px",
          cursor: "pointer",
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </div>
  );
}
