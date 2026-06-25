import type { Account } from "../../auth/types/authTypes";
import { AccountFileLibrary } from "../components/AccountFileLibrary";
import { MeetingAssetPlaybackPanel } from "../components/MeetingAssetPlaybackPanel";
import { MeetingIntelligenceResultPanel } from "../components/MeetingIntelligenceResultPanel";
import { MeetingActionPanel } from "../components/MeetingActionPanel";
import { MeetingChatPanel } from "../components/MeetingChatPanel";
import { MeetingCreateForm } from "../components/MeetingCreateForm";
import { MeetingList } from "../components/MeetingList";
import { useMeetingWorkspace } from "../hooks/useMeetingWorkspace";

type MeetingsScreenProps = {
  account: Account;
  requestedMeetingId: string | null;
  token: string;
  onSelectedMeetingChange: (meetingId: string | null) => void;
};

export function MeetingsScreen({
  onSelectedMeetingChange,
  requestedMeetingId,
  token
}: MeetingsScreenProps) {
  const workspace = useMeetingWorkspace(
    token,
    requestedMeetingId,
    onSelectedMeetingChange
  );

  return (
    <div className="workspace-screen">
      <aside className="workspace-sidebar">
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
        <AccountFileLibrary
          disabled={workspace.isLoading}
          files={workspace.accountFiles}
          playbackUrl={workspace.filePlaybackUrl}
          selectedFileId={workspace.selectedFileId}
          onDelete={workspace.deleteLibraryFile}
          onPlay={workspace.playLibraryFile}
          onRefresh={workspace.refreshAccountFiles}
          onUpload={workspace.uploadLibraryFile}
        />
      </aside>

      <div className="workspace-main">
        <MeetingActionPanel
          canProcess={workspace.canProcess}
          canUpload={workspace.canUpload}
          disabled={workspace.isLoading}
          hasLockedAsset={workspace.hasLockedAsset}
          isRecording={workspace.isRecording}
          lastAsset={workspace.lastAsset}
          latestJob={workspace.latestJob}
          selectedMeeting={workspace.selectedMeeting}
          onDeleteMeeting={workspace.deleteSelectedMeeting}
          onFileUpload={workspace.uploadFile}
          onProcess={workspace.queueProcessing}
          onRefreshStatus={workspace.refreshStatus}
          onStartRecording={workspace.startRecording}
          onStopRecording={workspace.stopRecording}
        />

        {workspace.selectedMeeting?.status === "READY" ? (
          <>
            <MeetingAssetPlaybackPanel asset={workspace.lastAsset} playbackUrl={workspace.assetPlaybackUrl} />
            <MeetingIntelligenceResultPanel result={workspace.intelligenceResult} />
            <MeetingChatPanel
              disabled={workspace.isLoading}
              messages={workspace.chatMessages}
              question={workspace.chatQuestion}
              selectedMeeting={workspace.selectedMeeting}
              onQuestionChange={workspace.setChatQuestion}
              onRefreshHistory={workspace.refreshChatHistory}
              onSubmitQuestion={workspace.submitChatQuestion}
            />
          </>
        ) : null}

        <div className="event-strip" aria-live="polite">
          <span className={workspace.error ? "event-strip__error" : ""}>
            {workspace.error ?? workspace.notice ?? "Ready"}
          </span>
        </div>
      </div>
    </div>
  );
}
