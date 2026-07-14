type MeetingProgressBarProps = {
  label: string;
  value?: number;
  indeterminate?: boolean;
};

export function MeetingProgressBar({ label, value, indeterminate = false }: MeetingProgressBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value ?? 0));

  return (
    <div className="meeting-progress" aria-label={label}>
      <div className="meeting-progress__label">{label}</div>
      <div
        className={`meeting-progress__track${indeterminate ? " meeting-progress__track--indeterminate" : ""}`}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        {...(!indeterminate ? { "aria-valuenow": Math.round(clampedValue) } : {})}
      >
        <div className="meeting-progress__fill" style={indeterminate ? undefined : { width: `${clampedValue}%` }} />
      </div>
      {!indeterminate && <span className="meeting-progress__value">{Math.round(clampedValue)}%</span>}
    </div>
  );
}
