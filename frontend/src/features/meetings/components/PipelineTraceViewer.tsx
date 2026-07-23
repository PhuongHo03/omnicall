import { useEffect, useRef } from "react";

import type { MeetingChatMessage } from "../types/meetingTypes";

export function PipelineTraceViewer({ isOpen, message, onToggle }: {
  isOpen: boolean;
  message: MeetingChatMessage;
  onToggle: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const trace = message.metadata.pipelineTrace;

  useEffect(() => {
    if (isOpen && containerRef.current) {
      const bubble = containerRef.current.closest(".chat-message");
      bubble?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [isOpen]);

  if (!trace) return null;
  return (
    <div className="flow" ref={containerRef}>
      <button aria-expanded={isOpen} className="sources__badge" type="button" onClick={onToggle}>
        <span>Steps{trace ? ` (${trace.stages.length})` : ""}</span>
        <span className={"sources__chevron" + (isOpen ? " sources__chevron--open" : "")}>&#9662;</span>
      </button>
      {isOpen ? (
        <div className="flow__panel flow__trace" role="tabpanel">
          {trace.stages.map((stage, index) => (
            <details className="flow__trace-json" open={stage.status === "failed"} key={`${stage.stage}-${index}`}>
              <summary>
                {stage.stage.replaceAll("_", " ")} · {stage.status} · {stage.durationMs} ms
                {stage.provider ? ` · ${stage.provider}${stage.model ? `/${stage.model}` : ""}` : ""}
              </summary>
              <pre>{JSON.stringify(stage.details, null, 2)}</pre>
            </details>
          ))}
        </div>
      ) : null}
    </div>
  );
}
