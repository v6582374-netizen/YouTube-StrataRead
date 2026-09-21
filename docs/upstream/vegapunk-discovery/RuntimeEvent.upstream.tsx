            return (
              <div key={item.sequence} className={`discovery-runtime-event discovery-runtime-event-in ${tone}`}>
                <span className="discovery-runtime-event-time">{prototypeActivityTime(item.occurred_at, item.sequence)}</span>
                <div className="discovery-runtime-event-copy">
                  <strong>{item.text}</strong>
                  <span>{milestone?.summary ?? (item.milestone_id ? `Milestone: ${item.milestone_id}` : "Launch event")}</span>
                </div>
                <span className="discovery-runtime-event-state">{stateLabel}</span>
              </div>
            );
