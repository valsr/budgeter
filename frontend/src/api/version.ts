import { formatTimestamp } from "../format";
import { apiFetch } from "./client";

export interface VersionInfo {
  /** Commit date plus short hash, e.g. "2026.10.07+5dcc9d3"; "unknown" if it can't be told. */
  version: string;
  sha: string | null;
  commit_date: string | null;
  /** Null when the server runs from source rather than a built image. */
  build_date: string | null;
  /** Running from a checkout with uncommitted changes. */
  dirty: boolean;
}

export const versionApi = {
  // Decoration, not function: if it fails the sidebar simply shows no version.
  get: () => apiFetch<VersionInfo>("/api/version", {}, { silent: true }),
};

/** The facts about a build, most identifying first, for whoever wants to list them. */
export function versionParts(v: VersionInfo): string[] {
  return [
    v.version,
    v.sha && `commit ${v.sha}`,
    v.commit_date && `committed ${formatTimestamp(v.commit_date)}`,
    v.build_date
      ? `built ${formatTimestamp(v.build_date)}`
      : "running from source" + (v.dirty ? ", with uncommitted changes" : ""),
  ].filter((part): part is string => Boolean(part));
}
