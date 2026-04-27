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
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Sources"]}
        onCmdK={onCmdK}
        actions={
          <button className="btn primary">
            <Icon name="plus" /> Add source
          </button>
        }
      />

      <div className="scroll">
        <div className="scroll-pad">
          <div className="h-eyebrow mb-8">Data integrations</div>
          <div className="h-display num" style={{ fontSize: 44 }}>
            {connected.length} connected · {channelsCount} channels
          </div>
          <div className="row gap-12 mt-12 mb-20">
            <Pill tone="pos" dot>
              all syncing
            </Pill>
            <Pill tone="info">last lab upload Mar 12, 2026</Pill>
          </div>

          {/* Connected */}
          <div className="section-head" style={{ paddingBottom: 12 }}>
            <div className="title">Connected</div>
            <div className="sub">{connected.length} active sources</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
            {connected.map((s) => (
              <SourceRow key={s.id} s={s} />
            ))}
          </div>

          {/* Available */}
          <div className="section-head mt-24" style={{ paddingBottom: 12 }}>
            <div className="title">Available</div>
            <div className="sub">{available.length} sources you could add</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
            {available.map((s) => (
              <SourceRow key={s.id} s={s} />
            ))}
          </div>

          {/* Privacy */}
          <div className="card tinted card-pad mt-24">
            <SectionHead title="Privacy" sub="How your data is handled" />
            <div className="text-2 fz-13" style={{ lineHeight: 1.6 }}>
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
    <div className="source-card">
      <SourceLogo color={s.color} mark={s.mark} size={40} />
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="row gap-8">
          <div className="title fz-13 fw-6">{s.name}</div>
          <Pill tone="default">{s.kind}</Pill>
          {s.connected && (
            <Pill tone="pos" dot>
              connected
            </Pill>
          )}
        </div>
        <div className="text-3 fz-12 mt-4">
          {s.channels.join(" · ")}
        </div>
      </div>
      <div className="text-3 fz-12" style={{ minWidth: 120, textAlign: "right" }}>
        {s.connected ? (
          <>
            <div>last sync</div>
            <div className="mono" style={{ color: "var(--ink-2)", fontWeight: 500 }}>{s.lastSync}</div>
          </>
        ) : (
          <span>not connected</span>
        )}
      </div>
      {s.connected ? (
        <button className="btn">Disconnect</button>
      ) : (
        <button className="btn primary">Connect</button>
      )}
    </div>
  );
}
