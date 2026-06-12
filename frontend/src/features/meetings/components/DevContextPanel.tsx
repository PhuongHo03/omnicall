import type { DevAuthContext } from "../types/meetingTypes";

type DevContextPanelProps = {
  context: DevAuthContext;
  onChange: (context: DevAuthContext) => void;
  disabled: boolean;
};

export function DevContextPanel({ context, disabled, onChange }: DevContextPanelProps) {
  return (
    <section className="tool-panel auth-panel">
      <div className="panel-heading">
        <h2>Context</h2>
      </div>
      <div className="context-grid">
        <label>
          <span>User ID</span>
          <input
            value={context.userId}
            disabled={disabled}
            onChange={(event) => onChange({ ...context, userId: event.target.value })}
          />
        </label>
        <label>
          <span>Workspace ID</span>
          <input
            value={context.workspaceId}
            disabled={disabled}
            onChange={(event) => onChange({ ...context, workspaceId: event.target.value })}
          />
        </label>
        <label>
          <span>User</span>
          <input
            value={context.userName}
            disabled={disabled}
            onChange={(event) => onChange({ ...context, userName: event.target.value })}
          />
        </label>
        <label>
          <span>Workspace</span>
          <input
            value={context.workspaceName}
            disabled={disabled}
            onChange={(event) => onChange({ ...context, workspaceName: event.target.value })}
          />
        </label>
      </div>
    </section>
  );
}
