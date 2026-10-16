/**
 * Import-job polling.
 *
 * A large upload is finished by a worker after the POST response already
 * returned (the request cannot stay open for minutes), so any screen that
 * shows a job keeps refreshing it until the status is terminal. Small files
 * still finish inside the request and never poll.
 */

/** Poll cadence while at least one visible job is still running. */
export const IMPORT_JOB_POLL_INTERVAL_MS = 3000

export function isImportJobLive(status: string): boolean {
  return status === "pending" || status === "processing"
}
