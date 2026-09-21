function PrototypeLaunchHero({
  launch,
  status,
}: {
  launch: DiscoveryLaunch | null;
  status: DiscoveryLaunchStatus | null;
}) {
  const standby = !launch;
  const milestones = status?.timeline.milestones ?? [];
  const currentMilestoneId = status?.timeline.current_milestone_id;
  const currentMilestone = milestones.find(
    (milestone) => milestone.id === currentMilestoneId || prototypeMilestoneState(milestone, currentMilestoneId) === "active",
  );
  const observedState = String(status?.state ?? launch?.state ?? "preparation");
  const observedStage = standby
    ? "Preparation"
    : prototypeLaunchStageLabel(status, currentMilestone?.summary ?? currentMilestone?.label ?? launch?.stage ?? "Preparation");
  const stateLabel = standby ? "Ready to launch" : prototypeLaunchStateLabel(observedState);
  const signalCopy =
    standby
      ? "Preparation is the current state. Confirm a Launch from Preparation when you are ready to begin."
      : observedState === "awaiting_review"
      ? "The run is paused at a deliberate human seam. Review the read-only bundle before resuming."
      : observedState === "failed"
        ? launch?.error
          ? `The Launch failed: ${launch.error}`
          : "The Launch failed before it produced a trusted terminal outcome. Open Current Launch for details."
      : observedState === "interrupted"
        ? "The worker stopped unexpectedly. Review the durable checkpoint before resuming."
      : observedState === "stopped"
        ? "The Launch was stopped at a durable checkpoint. Resume it when you are ready."
      : observedState === "completed"
        ? "The run is complete. Its timeline and artifacts remain available as immutable history."
        : "Evidence is moving through the current seam. The Launch remains interruptible and durable artifacts stay preserved.";
  return (
    <section className={`discovery-prototype-panel discovery-hero-panel discovery-beacon-hero ${standby ? "is-standby" : ""} ${observedState === "failed" || observedState === "interrupted" ? "is-error" : ""}`} aria-label="Current Discovery Launch">
      <div className="discovery-beacon-signal">
        <div className="discovery-beacon-signal-head">
          <div className="discovery-beacon-orb" aria-hidden="true"><span /></div>
          <div className="min-w-0">
            <div className="discovery-beacon-eyebrow">
              {standby ? "CURRENT OBSERVATION · PREPARATION" : `Live observation · round ${String(launch?.round ?? 0).padStart(2, "0")}`}
            </div>
            <h2 className="discovery-launch-title discovery-beacon-title">{observedStage}</h2>
            <p className="discovery-beacon-copy">{signalCopy}</p>
          </div>
        </div>
        <div className="discovery-beacon-track" aria-label="Launch timeline">
          <div className="discovery-beacon-track-head"><strong>Launch timeline</strong><span>semantic state rail</span></div>
          <div className="discovery-beacon-stage-list">
            {milestones.length ? milestones.map((milestone) => {
              const state = prototypeMilestoneState(milestone, currentMilestoneId);
              return (
                <div key={milestone.id} className={`discovery-beacon-stage is-${state}`}>
                  <strong>{milestone.label}</strong>
                  <span>{milestone.summary ?? (state === "done" ? "Completed" : state === "active" ? "In progress" : "Awaiting start")}</span>
                  <em>{state === "done" ? "DONE" : state === "active" ? "LIVE" : "NEXT"}</em>
                </div>
              );
            }) : (
              <div className={`discovery-beacon-stage ${standby ? "is-standby" : "is-active"}`}>
                <strong>{observedStage}</strong>
                <span>{standby ? "Waiting for a confirmed Launch" : "Waiting for the first durable timeline snapshot"}</span>
                <em>{standby ? "READY" : "LIVE"}</em>
              </div>
            )}
          </div>
        </div>
        {launch && <span className="sr-only">Launch {prototypeLaunchShortId(launch)}</span>}
        <span className="sr-only">{observedState}</span>
        {observedState === "awaiting_review" && <span className="sr-only">Execution inactive</span>}
      </div>
      <div className="discovery-beacon-metrics">
        <div className="discovery-beacon-metric"><span>State</span><strong>{stateLabel}</strong><small>server-authoritative</small></div>
        <div className="discovery-beacon-metric"><span>Elapsed</span><strong>{launch ? prototypeLaunchElapsed(launch) : "—"}</strong><small>since Launch start</small></div>
        <div className="discovery-beacon-metric"><span>Current seam</span><strong>{currentMilestone ? `${String(currentMilestone.position).padStart(2, "0")} / ${String(milestones.length).padStart(2, "0")}` : "—"}</strong><small>{currentMilestone?.label ?? observedStage}</small></div>
        <div className="discovery-beacon-metric"><span>Artifacts</span><strong>{status?.produced_outputs.length ?? 0}</strong><small>read-only references</small></div>
      </div>
    </section>
  );
}
