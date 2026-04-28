/**
 * Sources screen — connected wearables + lab provider cards.
 *
 * Each source is a card showing:
 *   - Logo tile (color + 2-letter mark)
 *   - Name + kind (Wearable / CGM / Lab / App)
 *   - Connection state (connected / not connected)
 *   - Last sync timestamp
 *   - Channels (HRV / RHR / Sleep / etc.)
 *   - Connect / Disconnect button
 *
 * Cards split into "Connected" and "Available" sections so the user can
 * scan their active integrations vs the catalog they could add.
 *
 * v1 is mock-only — buttons are stubs. Real version would deep-link to
 * each provider's OAuth flow.
 */
"use client";

import { Topbar, SectionHead, Pill, SourceLogo } from "../shared";
import { Icon } from "../icons";
import { SOURCES } from "../data";
import type { SourceCard } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenSources({ onCmdK }: ScreenProps) {
  const connected = SOURCES.filter((s) => s.connected);
  const available = SOURCES.filter((s) => !s.connected);

  // Quick stats for the hero
  const channelsCount = new Set(connected.flatMap((s) => s.channels)).size;

  return (
    <div className="cadence-content-col cadence-screen-fade">
      <Topbar
        crumbs={["Workspace", "Sources"]}
        onCmdK={onCmdK}
        actions={
          <button className="cadence-btn cadence-btn-primary">
            <Icon name="plus" /> Add source
          </button>
        }
      />

      <div className="cadence-scroll">
        <div className="cadence-scroll-pad">
          <div className="cadence-h-eyebrow cadence-mb-8">Data integrations</div>
          <div className="cadence-h-display cadence-num" style={{ fontSize: 44 }}>
            {connected.length} connected · {channelsCount} channels
          </div>
          <div className="cadence-row cadence-gap-12 cadence-mt-12 cadence-mb-20">
            <Pill tone="pos" dot>
              all syncing
            </Pill>
            <Pill tone="info">last lab upload Mar 12, 2026</Pill>
          </div>

          {/* Connected */}
          <div className="cadence-section-head" style={{ paddingBottom: 12 }}>
            <div className="cadence-title">Connected</div>
            <div className="cadence-sub">{connected.length} active sources</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
            {connected.map((s) => (
              <SourceRow key={s.id} s={s} />
            ))}
          </div>

          {/* Available */}
          <div className="cadence-section-head cadence-mt-24" style={{ paddingBottom: 12 }}>
            <div className="cadence-title">Available</div>
            <div className="cadence-sub">{available.length} sources you could add</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
            {available.map((s) => (
              <SourceRow key={s.id} s={s} />
            ))}
          </div>

          {/* Privacy */}
          <div className="cadence-card cadence-card-tinted cadence-card-pad cadence-mt-24">
            <SectionHead title="Privacy" sub="How your data is handled" />
            <div className="cadence-text-2 cadence-fz-13" style={{ lineHeight: 1.6 }}>
              Cadence stores your raw biomarker history locally and runs
              the rhyme finder on-device. Your data never leaves your
              browser unless you explicitly export it. There is no cohort
              learning, no cross-user comparison, no third-party
              advertising — just your body, on your machine.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface SourceRowProps {
  s: SourceCard;
}

function SourceRow({ s }: SourceRowProps) {
  return (
    <div className="cadence-source-card">
      <SourceLogo color={s.color} mark={s.mark} size={40} />
      <div className="cadence-grow" style={{ minWidth: 0 }}>
        <div className="cadence-row cadence-gap-8">
          <div className="cadence-title cadence-fz-13 cadence-fw-6">{s.name}</div>
          <Pill tone="default">{s.kind}</Pill>
          {s.connected && (
            <Pill tone="pos" dot>
              connected
            </Pill>
          )}
        </div>
        <div className="cadence-text-3 cadence-fz-12 cadence-mt-4">
          {s.channels.join(" · ")}
        </div>
      </div>
      <div className="cadence-text-3 cadence-fz-12" style={{ minWidth: 120, textAlign: "right" }}>
        {s.connected ? (
          <>
            <div>last sync</div>
            <div className="cadence-mono" style={{ color: "var(--ink-2)", fontWeight: 500 }}>{s.lastSync}</div>
          </>
        ) : (
          <span>not connected</span>
        )}
      </div>
      {s.connected ? (
        <button className="cadence-btn">Disconnect</button>
      ) : (
        <button className="cadence-btn cadence-btn-primary">Connect</button>
      )}
    </div>
  );
}
