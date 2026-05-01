/**
 * SavedRunsPanel — left-rail browser of saved goodruns.
 *
 * What this is for
 * ----------------
 * Saving a goodrun used to be a one-way trip: the AnalogDetailDrawer
 * POSTs to ``/goodruns`` and the record disappears from the user's view
 * forever. The workstation never showed that history again from inside
 * the workstation surface — to find a saved run, the user had to leave.
 *
 * This panel closes that loop. It renders a compact list of saved runs
 * (date · dataset · composite), and clicking a row hands the full
 * record back to the parent so the parent can restore the dataset +
 * window + (optionally) pinned analogs the user was looking at when
 * they saved.
 *
 * Source of records
 * -----------------
 * The parent owns the merged list (API + local mirror, API winning on
 * id collisions) and passes it in. This component is purely
 * presentational — it doesn't know whether the data came from
 * ``listGoodruns()`` or ``listLocalGoodruns()``. Keeping the merge
 * logic in the parent means a future "favorites" or "labelled-only"
 * filter can be added without changing this component's contract.
 *
 * UX contract
 * -----------
 *   - Empty state: explanatory copy, no controls.
 *   - 5 visible by default; "show N more" expands.
 *   - Each row shows: date (MMM D), dataset symbol, composite score
 *     formatted to 2 decimals. Wider screens get the full asset
 *     class via the title attribute on hover.
 *   - Click row → ``onRestore(record)``.
 *   - × → ``onDelete(id)``. The delete only removes the local mirror
 *     entry; the durable API record (if any) is unaffected. The
 *     parent decides whether to also call a remote delete.
 */

"use client";

import { useState } from "react";
import type { GoodrunRecord } from "../../lib/goodruns";

export interface SavedRunsPanelProps {
  /** Merged saved runs (API + local mirror), newest first. */
  records: GoodrunRecord[];
  /**
   * Called when the user clicks a row body. The parent should restore
   * the dataset and window indices from {@link GoodrunRecord} into the
   * live workstation state. Pinned-analog restoration is the parent's
   * call too — the record carries enough to do it (the saved
   * ``match_id`` + the recorded ``query`` window).
   */
  onRestore: (record: GoodrunRecord) => void;
  /**
   * Called when the user clicks ×. By contract this only removes the
   * local-mirror copy — the API record is durable. If a remote-delete
   * endpoint exists in the future, the parent can chain it.
   */
  onDelete: (id: string) => void;
}

/** How many rows we show before requiring "show more". */
const COLLAPSED_LIMIT = 5;

export function SavedRunsPanel({
  records,
  onRestore,
  onDelete,
}: SavedRunsPanelProps): React.ReactElement {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? records : records.slice(0, COLLAPSED_LIMIT);
  const hidden = Math.max(0, records.length - COLLAPSED_LIMIT);

  return (
    <div className="side__section">
      <div className="side__header">
        <span className="label">Saved runs</span>
        <span
          className="mono"
          style={{ fontSize: 10.5, color: "var(--ink-3)" }}
        >
          {records.length}
        </span>
      </div>

      {records.length === 0 ? (
        <div
          className="serif"
          style={{
            fontSize: 12,
            color: "var(--ink-3)",
            fontStyle: "italic",
          }}
        >
          Save a run from the analog detail drawer to keep it here.
          Click any saved row to restore its window.
        </div>
      ) : (
        <div className="saved-list">
          {visible.map((r) => (
            <SavedRunRow
              key={r.id}
              record={r}
              onRestore={onRestore}
              onDelete={onDelete}
            />
          ))}
          {hidden > 0 && (
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
              {expanded ? "show fewer" : `show ${hidden} more`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

interface SavedRunRowProps {
  record: GoodrunRecord;
  onRestore: (record: GoodrunRecord) => void;
  onDelete: (id: string) => void;
}

/**
 * One saved-run row. The row body acts as a button (click → restore);
 * the × stops propagation so deleting doesn't also restore.
 *
 * Date formatting: we render ``saved_at`` as ``MMM D`` because the
 * rail is narrow and most saves are recent (this-quarter resolution
 * is fine). The full ISO string is on the title attribute for
 * power-user hover.
 */
function SavedRunRow({
  record,
  onRestore,
  onDelete,
}: SavedRunRowProps): React.ReactElement {
  const dateLabel = (() => {
    try {
      return new Date(record.saved_at).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
    } catch {
      return "—";
    }
  })();

  /**
   * Compact dataset display. ``dataset`` is a slash-joined triple
   * ``{class}/{symbol}/{tf}``; the rail shows the symbol uppercased
   * because that's what the user thinks in. Class + timeframe go to
   * the title attr.
   */
  const parts = record.dataset.split("/");
  const symbol = (parts[1] ?? record.dataset).toUpperCase();
  const titleSuffix = parts.length === 3 ? ` · ${parts[0]}/${parts[2]}` : "";

  const composite =
    typeof record.composite === "number" && Number.isFinite(record.composite)
      ? record.composite.toFixed(2)
      : "—";

  return (
    <div
      className="saved"
      role="button"
      tabIndex={0}
      onClick={() => onRestore(record)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onRestore(record);
        }
      }}
      title={`${record.saved_at} · ${symbol}${titleSuffix} · composite ${composite}`}
    >
      <span className="saved__date">{dateLabel}</span>
      <span className="saved__name">{symbol}</span>
      <span className="saved__score">{composite}</span>
      <button
        aria-label="Forget saved run"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(record.id);
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
