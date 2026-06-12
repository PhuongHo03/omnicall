import { useState } from "react";

import { DevContextPanel } from "../components/DevContextPanel";
import { MeetingActionPanel } from "../components/MeetingActionPanel";
import { MeetingChatPanel } from "../components/MeetingChatPanel";
import { MeetingCreateForm } from "../components/MeetingCreateForm";
import { MeetingList } from "../components/MeetingList";
import { useMeetingWorkspace } from "../hooks/useMeetingWorkspace";

type DetailTab = "operations" | "chat";

export function MeetingsScreen() {
  const workspace = useMeetingWorkspace();
  const [activeDetailTab, setActiveDetailTab] = useState<DetailTab>("operations");

  return (
    <div className="workspace-screen">
      <div className="workspace-rail">
        <DevContextPanel
          context={workspace.authContext}
          disabled={workspace.isLoading}
          onChange={workspace.setAuthContext}
        />
        <MeetingCreateForm
          draft={workspace.draft}
          disabled={workspace.isLoading}
          onChange={workspace.setDraft}
          onSubmit={workspace.submitMeeting}
        />
        <MeetingList
          disabled={workspace.isLoading}
          meetings={workspace.meetings}
          selectedMeetingId={workspace.selectedMeetingId}
          onRefresh={workspace.refreshMeetings}
          onSelect={workspace.setSelectedMeetingId}
        />
      </div>

      <div className="workspace-main">
        <div className="detail-tabs" role="tablist" aria-label="Meeting workspace views">
          <button
            type="button"
            role="tab"
            aria-selected={activeDetailTab === "operations"}
            className={activeDetailTab === "operations" ? "detail-tabs__item detail-tabs__item--active" : "detail-tabs__item"}
            onClick={() => setActiveDetailTab("operations")}
          >
            Operations
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeDetailTab === "chat"}
            className={activeDetailTab === "chat" ? "detail-tabs__item detail-tabs__item--active" : "detail-tabs__item"}
            onClick={() => setActiveDetailTab("chat")}
          >
            Chat
          </button>
        </div>

        {activeDetailTab === "operations" ? (
          <MeetingActionPanel
            disabled={workspace.isLoading}
            isRecording={workspace.isRecording}
            lastAsset={workspace.lastAsset}
            latestJob={workspace.latestJob}
            selectedMeeting={workspace.selectedMeeting}
            onFileUpload={workspace.uploadFile}
            onProcess={workspace.queueProcessing}
            onRefreshStatus={workspace.refreshStatus}
            onStartRecording={workspace.startRecording}
            onStopRecording={workspace.stopRecording}
          />
        ) : (
          <MeetingChatPanel
            disabled={workspace.isLoading}
            messages={workspace.chatMessages}
            question={workspace.chatQuestion}
            selectedMeeting={workspace.selectedMeeting}
            sessionId={workspace.chatSessionId}
            onQuestionChange={workspace.setChatQuestion}
            onRefreshHistory={workspace.refreshChatHistory}
            onSubmitQuestion={workspace.submitChatQuestion}
          />
        )}

        <div className="event-strip" aria-live="polite">
          <span className={workspace.error ? "event-strip__error" : ""}>
            {workspace.error ?? workspace.notice ?? "Ready"}
          </span>
        </div>
      </div>
    </div>
  );
}
