import { useEffect, useRef } from "react";
import { EmptyState } from "../../../shared/components/EmptyState";

import type { TranscriptEntry } from "../types/meetingTypes";
import { formatTime } from "../utils/meetingFormatters";

type TranscriptTrackProps = {
  entries: TranscriptEntry[];
  activeIndex: number;
  progressWithinEntry: number;
  onSeekToEntry: (entry: TranscriptEntry) => void;
};

export function TranscriptTrack({
  entries,
  activeIndex,
  progressWithinEntry,
  onSeekToEntry,
}: TranscriptTrackProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);

  // Auto-scroll active entry into view
  useEffect(() => {
    if (activeRef.current && listRef.current) {
      const container = listRef.current;
      const element = activeRef.current;
      const containerRect = container.getBoundingClientRect();
      const elementRect = element.getBoundingClientRect();

      if (elementRect.top < containerRect.top || elementRect.bottom > containerRect.bottom) {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [activeIndex]);

  return (
    <div className="apb-transcript">
      {entries.length === 0 ? (
        <EmptyState message="No transcript available." />
      ) : (
        <>
          <div className="apb-transcript__header">
            <span>Transcript</span>
            <span className="apb-transcript__count">{entries.length} segments</span>
          </div>
          <div className="apb-transcript__list" ref={listRef}>
            {entries.map((entry, index) => {
              const isActive = index === activeIndex;
              return (
                <div
                  key={entry.id}
                  ref={isActive ? activeRef : undefined}
                  className={`apb-transcript__entry${isActive ? " apb-transcript__entry--active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSeekToEntry(entry)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSeekToEntry(entry); }}
                >
                  {isActive && (
                    <div
                      className="apb-transcript__entry-progress"
                      style={{ width: `${progressWithinEntry * 100}%` }}
                    />
                  )}
                  <div className="apb-transcript__entry-head">
                    <span className="apb-transcript__speaker">{entry.speaker}</span>
                    <span className="apb-transcript__time">
                      {formatTime(entry.startMs / 1000)} – {formatTime(entry.endMs / 1000)}
                    </span>
                  </div>
                  <p className="apb-transcript__text">{entry.text}</p>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
