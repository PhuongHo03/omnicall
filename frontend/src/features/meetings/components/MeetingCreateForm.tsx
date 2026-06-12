import { Plus } from "lucide-react";

import { IconButton } from "../../../components/IconButton";
import type { MeetingDraft } from "../types/meetingTypes";

type MeetingCreateFormProps = {
  draft: MeetingDraft;
  disabled: boolean;
  onChange: (draft: MeetingDraft) => void;
  onSubmit: () => void;
};

export function MeetingCreateForm({ disabled, draft, onChange, onSubmit }: MeetingCreateFormProps) {
  const canSubmit = draft.title.trim().length > 0 && !disabled;

  return (
    <section className="tool-panel">
      <div className="panel-heading">
        <h2>New Meeting</h2>
      </div>
      <div className="create-grid">
        <label>
          <span>Title</span>
          <input
            value={draft.title}
            maxLength={240}
            disabled={disabled}
            onChange={(event) => onChange({ ...draft, title: event.target.value })}
          />
        </label>
        <label>
          <span>Language</span>
          <select
            value={draft.language}
            disabled={disabled}
            onChange={(event) => onChange({ ...draft, language: event.target.value })}
          >
            <option value="vi">vi</option>
            <option value="en">en</option>
          </select>
        </label>
        <IconButton icon={<Plus size={16} />} label="Create" disabled={!canSubmit} onClick={onSubmit} variant="primary" />
      </div>
    </section>
  );
}
