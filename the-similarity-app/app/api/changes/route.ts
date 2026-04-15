/**
 * /api/changes — recent project activity feed for the Reports page.
 *
 * Returns a merged list of:
 *   - recent git commits on the local main branch
 *   - recently merged/open pull requests (via `gh` CLI, if available)
 *
 * Runs on the server only. Shells out with a strict timeout and falls
 * back to empty arrays on failure so the UI never crashes if git/gh
 * are unavailable. The payload is cached for 60 seconds to keep the
 * response cheap on page navigations.
 */

import { NextResponse } from "next/server";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { resolve } from "node:path";

const execFile = promisify(execFileCb);

export const revalidate = 60;

// Run `git log` from the repo root, two levels up from the app dir.
const REPO_ROOT = resolve(process.cwd(), "..");

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

async function readRecentCommits(limit = 40): Promise<Commit[]> {
  try {
    // Field separator chosen to be extremely unlikely to appear in a
    // commit subject, author, or date. Record separator is newline.
    const FS = "\x1f";
    const format = ["%H", "%h", "%s", "%an", "%ai", "%d"].join(FS);
    const { stdout } = await execFile(
      "git",
      ["log", `--pretty=format:${format}`, `-n`, String(limit)],
      { cwd: REPO_ROOT, timeout: 5_000, maxBuffer: 2 * 1024 * 1024 },
    );
    return stdout
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        const [hash, shortHash, subject, author, date, refs] = line.split(FS);
        return {
          hash: hash ?? "",
          shortHash: shortHash ?? "",
          subject: subject ?? "",
          author: author ?? "",
          date: date ?? "",
          refs: (refs ?? "").trim(),
        };
      });
  } catch {
    return [];
  }
}

async function readRecentPullRequests(limit = 20): Promise<PullRequest[]> {
  try {
    const { stdout } = await execFile(
      "gh",
      [
        "pr",
        "list",
        "--state",
        "all",
        "--limit",
        String(limit),
        "--json",
        "number,title,url,state,mergedAt,createdAt,author",
      ],
      { cwd: REPO_ROOT, timeout: 8_000, maxBuffer: 2 * 1024 * 1024 },
    );
    const rows: Array<{
      number: number;
      title: string;
      url: string;
      state: string;
      mergedAt: string | null;
      createdAt: string;
      author: { login: string };
    }> = JSON.parse(stdout);
    return rows.map((row) => ({
      number: row.number,
      title: row.title,
      url: row.url,
      // Coerce state into the narrow union; unknown values treated as CLOSED.
      state:
        row.state === "OPEN" || row.state === "MERGED" || row.state === "CLOSED"
          ? row.state
          : "CLOSED",
      mergedAt: row.mergedAt,
      createdAt: row.createdAt,
      author: row.author?.login ?? "unknown",
    }));
  } catch {
    return [];
  }
}

export async function GET() {
  const [commits, pullRequests] = await Promise.all([
    readRecentCommits(),
    readRecentPullRequests(),
  ]);
  return NextResponse.json(
    {
      commits,
      pullRequests,
      generatedAt: new Date().toISOString(),
    },
    {
      headers: {
        // Cache on the edge for 60s; stale-while-revalidate for 5 min.
        "Cache-Control":
          "public, s-maxage=60, stale-while-revalidate=300",
      },
    },
  );
}
