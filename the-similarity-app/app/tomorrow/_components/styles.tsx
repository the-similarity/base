export const TOMORROW_CSS = `
.tomorrow-app {
  --app-bg: #ffffff;
  --sidebar: rgba(255,255,255,0.74);
  --panel: #ffffff;
  --text: #181816;
  --ink: #181816;
  --muted: #686b64;
  --faint: #9a9c93;
  --line: rgba(24,24,22,0.10);
  --line-mid: rgba(24,24,22,0.16);
  --hover: rgba(10,107,72,0.08);
  --accent: #0a6b48;
  --accent-mid: #8fc4aa;
  --accent-soft: #e7f0ea;
  --accent-ink: #075437;
  --warm: #b07c1d;
  --warm-strong: #b14a3a;
  --warm-soft: #f4dfc1;
  --cool: #2e5d8c;
  --green: #0a6b48;
  --rail: rgba(18, 22, 18, 0.88);
  --rail-ink: rgba(255,255,255,0.62);
  --rail-active: rgba(255,255,255,0.12);
  --radius-card: 8px;
  --radius-control: 7px;
  --shadow-card: 0 18px 46px -32px rgba(28, 25, 18, 0.55);
  font-family: -apple-system, BlinkMacSystemFont, 'Trebuchet MS', Roboto, Ubuntu, sans-serif;
  position: relative;
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--app-bg);
}

.tomorrow-app.tomorrow-dark {
  --app-bg: #000000;
  --sidebar: rgba(20,23,20,0.78);
  --panel: #171a17;
  --text: #edeee9;
  --ink: #f4f5ee;
  --muted: #a3a79d;
  --faint: #71766d;
  --line: rgba(244,245,238,0.11);
  --line-mid: rgba(244,245,238,0.18);
  --hover: rgba(44,136,98,0.16);
  --accent: #2c8862;
  --accent-mid: #68b790;
  --accent-soft: #193628;
  --accent-ink: #8fd0ad;
  --warm-soft: #3d2c18;
  --rail: rgba(7, 9, 7, 0.92);
  --rail-ink: rgba(255,255,255,0.58);
  --rail-active: rgba(255,255,255,0.14);
}

.tomorrow-painterly {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: var(--app-bg);
}

.tomorrow-shell {
  position: relative;
  z-index: 1;
  min-height: 100vh;
  padding: 14px;
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  gap: 14px;
}

.tomorrow-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 2px;
}

.tomorrow-sidebar {
  position: sticky;
  top: 14px;
  height: calc(100vh - 28px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.46);
  border-radius: 14px;
  background: var(--sidebar);
  backdrop-filter: blur(20px) saturate(125%);
  box-shadow: var(--shadow-card);
}

.tomorrow-sidebar__brand {
  padding: 16px 14px 14px;
  border-bottom: 1px solid var(--line);
  display: grid;
  grid-template-columns: 34px 1fr;
  gap: 10px;
  align-items: center;
}

.tomorrow-brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: var(--accent);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--mono);
  font-weight: 700;
  font-size: 12px;
}

.tomorrow-brand-name {
  font-size: 18px;
  line-height: 1.05;
  font-style: italic;
  font-weight: 650;
  color: var(--ink);
}

.tomorrow-brand-sub {
  margin-top: 3px;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.tomorrow-sidebar__body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.tomorrow-compose-button {
  width: 100%;
  justify-content: flex-start;
  gap: 8px;
  padding: 8px 10px;
}

.tomorrow-compose-icon {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.14);
  color: currentColor;
  line-height: 1;
  flex: 0 0 auto;
}

.tomorrow-sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tomorrow-nav-main {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.tomorrow-nav-item,
.tomorrow-button {
  min-height: 32px;
  border-radius: var(--radius-control);
  display: inline-flex;
  align-items: center;
  gap: 9px;
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
  transition: background 100ms ease, color 100ms ease, border-color 100ms ease;
}

.tomorrow-nav-item {
  justify-content: space-between;
  padding: 7px 9px;
}

.tomorrow-nav-item[data-active="true"] {
  background: var(--hover);
  color: var(--ink);
}

.tomorrow-button {
  justify-content: center;
  padding: 7px 11px;
  border: 1px solid var(--line-mid);
  background: var(--panel);
  color: var(--ink);
}

.tomorrow-button[data-variant="primary"] {
  background: var(--ink);
  border-color: var(--ink);
  color: var(--app-bg);
}

.tomorrow-button[data-variant="ghost"] {
  background: transparent;
  color: var(--muted);
}

.tomorrow-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  background: var(--panel);
  box-shadow: var(--shadow-card);
}

.tomorrow-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border-radius: 999px;
  padding: 3px 8px;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--accent-ink);
  background: var(--accent-soft);
}

.tomorrow-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(135deg, #0a6b48, #b07c1d);
  font-size: 11px;
  font-weight: 700;
}

.tomorrow-empty-state {
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  background: var(--panel);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: var(--muted);
}

.tomorrow-app section[style*="var(--panel)"],
.tomorrow-app .entry-card,
.tomorrow-app .rhyme-pair-card,
.tomorrow-app .archetype-card {
  box-shadow: var(--shadow-card);
}

@media (max-width: 1280px) {
  .tomorrow-shell {
    grid-template-columns: 68px minmax(0, 1fr);
    gap: 12px;
    padding: 12px;
  }

  .tomorrow-sidebar {
    position: sticky;
    top: 12px;
    height: calc(100vh - 24px);
    border-radius: 10px;
  }

  .tomorrow-sidebar__brand {
    padding: 12px 10px;
    display: flex;
    justify-content: center;
  }

  .tomorrow-sidebar__brand > div:last-child {
    display: none;
  }

  .tomorrow-sidebar__body {
    flex-direction: column;
    overflow: hidden;
    align-items: stretch;
    gap: 10px;
    padding: 10px;
  }

  .tomorrow-sidebar__nav {
    min-width: 0;
    flex-direction: column;
    gap: 4px;
  }

  .tomorrow-compose-button {
    width: 100%;
    min-width: 0;
    justify-content: center;
    padding: 8px 0;
  }

  .tomorrow-compose-label,
  .tomorrow-nav-label,
  .tomorrow-nav-hint,
  .tomorrow-export-label,
  .tomorrow-status-badge,
  .tomorrow-local-row {
    display: none !important;
  }

  .tomorrow-compose-icon {
    background: transparent;
  }

  .tomorrow-nav-item {
    justify-content: center;
    padding: 9px 0;
  }

  .tomorrow-nav-main {
    gap: 0;
  }

  .tomorrow-sidebar__footer {
    align-items: stretch;
  }

  .tomorrow-export-button {
    justify-content: center !important;
    padding: 9px 0;
  }
}

@media (max-width: 760px) {
  .tomorrow-shell {
    grid-template-columns: 1fr;
    padding: 8px;
  }

  .tomorrow-sidebar {
    position: relative;
    top: 0;
    height: auto;
  }

  .tomorrow-sidebar__brand {
    display: flex;
    padding: 8px 10px 0;
    border-bottom: 0;
  }

  .tomorrow-sidebar__body {
    flex-direction: row;
    overflow-x: auto;
    gap: 6px;
    padding: 8px;
  }

  .tomorrow-sidebar__nav {
    flex-direction: row;
    min-width: max-content;
  }

  .tomorrow-compose-button,
  .tomorrow-nav-item,
  .tomorrow-export-button {
    min-width: 40px;
  }

  .tomorrow-sidebar__footer {
    display: none !important;
  }
}
`;
