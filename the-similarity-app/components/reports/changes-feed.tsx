"use client";

import { useEffect, useState } from "react";

type Commit = {
  hash: string;
  shortHash: string;
  subject: string;
  author: string;
  date: string;
  refs: string;
};

type PullRequest = {
  number: number;
  title: string;
  url: string;
  state: "OPEN" | "MERGED" | "CLOSED";
  mergedAt: string | null;
  createdAt: string;
  author: string;
};

type ChangesPayload = {
  commits: Commit[];
  pullRequests: PullRequest[];
  generatedAt: string;
};

type FeedItem =
  | { kind: "commit"; at: string; commit: Commit }
  | { kind: "pr"; at: string; pr: PullRequest };

/**
 * Merge commits + PRs into a single time-sorted feed. PRs use their
 * mergedAt if present, otherwise createdAt — so open PRs still surface
 * at the point they were opened. Commits use the raw author date. Both
 * are ISO-ish strings ordered lexicographically (good enough for
 * single-timezone repos).
 */
function mergeFeed(payload: ChangesPayload): FeedItem[] {
  const commits: FeedItem[] = payload.commits.map((commit) => ({
    kind: "commit" as const,
    at: commit.date,
    commit,
  }));
  const prs: FeedItem[] = payload.pullRequests.map((pr) => ({
    kind: "pr" as const,
    at: pr.mergedAt ?? pr.createdAt,
    pr,
  }));
  return [...commits, ...prs].sort((a, b) => (a.at < b.at ? 1 : -1));
}

export function ChangesFeed() {
  const [payload, setPayload] = useState<ChangesPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // The API route is cached on the server for 60s; no need to
    // aggressively re-fetch on the client.
    fetch("/api/changes")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: ChangesPayload) => {
        if (!cancelled) setPayload(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "unknown error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="reports-feed-empty">
        Activity feed unavailable ({error}). The API route shells out to{" "}
        <code>git</code> and <code>gh</code>; they may not be on the PATH
        in this environment.
      </div>
    );
  }

  if (!payload) {
    return <div className="reports-feed-empty">Loading activity…</div>;
  }

  const items = mergeFeed(payload);
  if (items.length === 0) {
    return (
      <div className="reports-feed-empty">
        No recent activity detected.
      </div>
    );
  }

  return (
    <ul className="reports-feed">
      {items.map((item) => (
        <FeedRow key={item.kind === "commit" ? item.commit.hash : `pr-${item.pr.number}`} item={item} />
      ))}
    </ul>
  );
}

function FeedRow({ item }: { item: FeedItem }) {
  if (item.kind === "commit") {
    const { commit } = item;
    return (
      <li className="reports-feed__row reports-feed__row--commit">
        <span className="reports-feed__kind reports-feed__kind--commit">commit</span>
        <span className="reports-feed__hash">{commit.shortHash}</span>
        <span className="reports-feed__subject">{commit.subject}</span>
        <span className="reports-feed__author">{commit.author}</span>
        <span className="reports-feed__date">{formatDate(commit.date)}</span>
      </li>
    );
  }
  const { pr } = item;
  const stateClass =
    pr.state === "MERGED"
      ? "merged"
      : pr.state === "OPEN"
        ? "open"
        : "closed";
  return (
    <li className={`reports-feed__row reports-feed__row--pr`}>
      <span className={`reports-feed__kind reports-feed__kind--pr-${stateClass}`}>
        PR {pr.state.toLowerCase()}
      </span>
      <span className="reports-feed__hash">#{pr.number}</span>
      <a
        href={pr.url}
        target="_blank"
        rel="noopener"
        className="reports-feed__subject reports-feed__subject--link"
      >
        {pr.title}
      </a>
      <span className="reports-feed__author">{pr.author}</span>
      <span className="reports-feed__date">{formatDate(item.at)}</span>
    </li>
  );
}

function formatDate(raw: string): string {
  // Dates arrive either as `YYYY-MM-DDTHH:mm:ssZ` (PR) or
  // `YYYY-MM-DD HH:mm:ss ±zzzz` (git). Slice to the calendar date
  // portion so the row stays readable.
  if (!raw) return "";
  const datePart = raw.slice(0, 10);
  return datePart;
}
