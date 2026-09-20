export function presentationStateForTaskStatus(status) {
  if (status === "failed") return "terminal_failure_recovery";
  if (status === "completed") return "success";
  if (status === "needs_input" || status === "needs input" || status === "awaiting_authorization" || status === "awaiting authorization") {
    return "awaiting_input";
  }
  if (status === "queued" || status === "running") return "working";
  return "idle";
}

export function sceneDurationForMotion(mode, prefersReducedMotion) {
  if (mode === "off") return 0;
  if (mode === "tableau" || prefersReducedMotion) return 1400;
  return 9800;
}
