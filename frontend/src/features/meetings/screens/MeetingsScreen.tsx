import { useCallback, useEffect, useState } from "react";
import { EmptyState } from "../../../shared/components/EmptyState";

import { useSidebarSlot } from "../../../shared/layouts/SidebarContext";
import { PlaybackDrawer } from "../components/PlaybackDrawer";
import { ResultDrawer } from "../components/ResultDrawer";
import { MeetingActionPanel } from "../components/MeetingActionPanel";
import { MeetingChatPanel } from "../components/MeetingChatPanel";
import { MeetingList } from "../components/MeetingList";
import { MeetingProgressBar } from "../components/MeetingProgressBar";
import { MeetingRecordingStatus } from "../components/MeetingRecordingStatus";
import { useMeetingWorkspace } from "../hooks/useMeetingWorkspace";
import { meetingFailurePresentation } from "../states/meetingState";
import type { MeetingChatCitation, PlaybackSeekRequest } from "../types/meetingTypes";

type MeetingsScreenProps = {
  requestedMeetingId: string | null;
  token: string;
  userId: string;
  onSelectedMeetingChange: (meetingId: string | null) => void;
};

export function MeetingsScreen({
  onSelectedMeetingChange,
  requestedMeetingId,
  token,
  userId,
}: MeetingsScreenProps) {
  const workspace = useMeetingWorkspace(
    userId,
    token,
    requestedMeetingId,
    onSelectedMeetingChange
  );

  const [isResultDrawerOpen, setIsResultDrawerOpen] = useState(false);
  const openResultDrawer = useCallback(() => setIsResultDrawerOpen(true), []);
  const closeResultDrawer = useCallback(() => setIsResultDrawerOpen(false), []);

  const [isPlaybackDrawerOpen, setIsPlaybackDrawerOpen] = useState(false);
  const [seekRequest, setSeekRequest] = useState<PlaybackSeekRequest | null>(null);
  const openPlaybackDrawer = useCallback(() => setIsPlaybackDrawerOpen(true), []);
  const closePlaybackDrawer = useCallback(() => setIsPlaybackDrawerOpen(false), []);
  const openCitationPlayback = useCallback((citation: MeetingChatCitation) => {
    setSeekRequest({
      startMs: citation.startMs,
      endMs: citation.endMs,
      segmentIds: citation.segmentIds,
    });
    setIsPlaybackDrawerOpen(true);
  }, []);

  const { setCreateMeetingDisabled, setExtraContent, setOnCreateMeeting } = useSidebarSlot();

  useEffect(() => {
    setOnCreateMeeting(() => workspace.createNewMeeting);
    return () => setOnCreateMeeting(null);
  }, [workspace.createNewMeeting, setOnCreateMeeting]);

  useEffect(() => {
    setCreateMeetingDisabled(workspace.isOperationLocked);
    return () => setCreateMeetingDisabled(false);
  }, [setCreateMeetingDisabled, workspace.isOperationLocked]);

  useEffect(() => {
    setIsPlaybackDrawerOpen(false);
    setIsResultDrawerOpen(false);
    setSeekRequest(null);
  }, [workspace.selectedMeetingId]);

  useEffect(() => {
    setExtraContent(
      <MeetingList
        disabled={workspace.isLoading || workspace.isOperationLocked}
        meetings={workspace.meetings}
        selectedMeetingId={workspace.selectedMeetingId}
        onCreate={workspace.createNewMeeting}
        onSelect={workspace.setSelectedMeetingId}
      />
    );
    return () => setExtraContent(null);
  }, [workspace.isLoading, workspace.isOperationLocked, workspace.meetings, workspace.selectedMeetingId, workspace.createNewMeeting, workspace.setSelectedMeetingId, setExtraContent]);

  if (!workspace.selectedMeeting) {
    if (workspace.recordingSession) {
      return (
        <div className="workspace-screen">
          <MeetingRecordingStatus
            session={workspace.recordingSession}
            uploadProgress={workspace.uploadProgress}
            canRetry={workspace.meetings.some((meeting) => meeting.id === workspace.recordingSession?.meetingId && meeting.status === "DRAFT" && !meeting.latestAsset)}
            onDiscard={workspace.discardRecording}
            onDownload={workspace.downloadRecording}
            onRetry={workspace.retryRecordingUpload}
          />
        </div>
      );
    }
    return (
      <div className="workspace-screen">
        <EmptyState icon="📋" message="Select a meeting" description="Choose a meeting from the sidebar or create a new one." className="empty-state--hero" />
      </div>
    );
  }

  const meetingStatus = workspace.selectedMeeting.status;
  const isUploading = workspace.uploadProgress !== null;
  const showProcessingProgress = meetingStatus === "QUEUED" || meetingStatus === "PROCESSING";

  const renderMeetingState = () => {
    if (workspace.recordingSession?.meetingId === workspace.selectedMeetingId) {
      return (
        <MeetingRecordingStatus
          session={workspace.recordingSession}
          uploadProgress={workspace.uploadProgress}
          canRetry={workspace.meetings.some((meeting) => meeting.id === workspace.recordingSession?.meetingId && meeting.status === "DRAFT" && !meeting.latestAsset)}
          onDiscard={workspace.discardRecording}
          onDownload={workspace.downloadRecording}
          onRetry={workspace.retryRecordingUpload}
        />
      );
    }
    if (meetingStatus === "READY") {
      return (
        <MeetingChatPanel
          disabled={workspace.isLoading}
          messages={workspace.chatMessages}
          question={workspace.chatQuestion}
          onQuestionChange={workspace.setChatQuestion}
          typewriterMessageIds={workspace.typewriterMessageIds}
          onTypewriterComplete={workspace.clearTypewriterId}
          onSubmitQuestion={workspace.submitChatQuestion}
          onFeedback={workspace.submitChatFeedback}
          pendingFeedbackMessageIds={workspace.pendingFeedbackMessageIds}
          onCitationClick={openCitationPlayback}
        />
      );
    }

    if (isUploading) {
      return (
        <EmptyState message="Đang tải tệp lên...">
          <MeetingProgressBar label="Upload progress" value={workspace.uploadProgress ?? 0} />
        </EmptyState>
      );
    }

    if (showProcessingProgress) {
      return (
        <EmptyState message={meetingStatus === "QUEUED" ? "Đang chờ xử lý..." : "Đang xử lý meeting..."}>
          <MeetingProgressBar
            label={meetingStatus === "QUEUED" ? "Processing queue" : "Meeting processing"}
            indeterminate
          />
        </EmptyState>
      );
    }

    if (meetingStatus === "FAILED") {
      const failure = meetingFailurePresentation(workspace.selectedMeeting?.failureCode ?? null);
      return <EmptyState message={failure.message} description={failure.description} />;
    }

    const messageByStatus = {
      DRAFT: "Tải tệp âm thanh để bắt đầu",
      UPLOADED: "Tệp đã tải lên, nhấn Process để bắt đầu",
    } as const;

    return <EmptyState message={messageByStatus[meetingStatus as keyof typeof messageByStatus] ?? "Upload and process a meeting to start chatting."} />;
  };

  return (
    <div className="workspace-screen">
      <div className="workspace-main">
        <MeetingActionPanel
          canProcess={workspace.canProcess}
          canUpload={workspace.canUpload}
          canViewResult={workspace.selectedMeeting.status === "READY" && workspace.intelligenceResult !== null}
          hasAsset={workspace.lastAsset !== null}
          isProcessing={workspace.isLoading}
          isRefreshingStatus={false}
          isUploading={workspace.uploadProgress !== null}
          isRecording={workspace.isRecording}
          isOperationLocked={workspace.isOperationLocked}
          recordingPhase={workspace.recordingSession?.phase ?? "idle"}
          selectedMeeting={workspace.selectedMeeting}
          onDeleteMeeting={workspace.deleteSelectedMeeting}
          onFileUpload={workspace.uploadFile}
          onOpenPlayback={openPlaybackDrawer}
          onProcess={workspace.queueProcessing}
          onRefreshStatus={workspace.refreshStatus}
          onRenameMeeting={workspace.renameSelectedMeeting}
          onStartRecording={workspace.startRecording}
          onStopRecording={workspace.stopRecording}
          onViewResult={openResultDrawer}
        />

        {renderMeetingState()}

        <ResultDrawer
          isOpen={isResultDrawerOpen}
          result={workspace.intelligenceResult}
          onClose={closeResultDrawer}
        />
        <PlaybackDrawer
          key={`${workspace.selectedMeetingId ?? "none"}:${workspace.lastAsset?.id ?? "none"}`}
          isOpen={isPlaybackDrawerOpen}
          asset={workspace.lastAsset}
          playbackUrl={workspace.assetPlaybackUrl}
          playbackStatus={workspace.assetPlaybackStatus}
          playbackError={workspace.assetPlaybackError}
          transcriptEntries={workspace.transcriptEntries}
          onDownload={workspace.downloadAsset}
          onClose={closePlaybackDrawer}
          seekRequest={seekRequest}
        />
      </div>
    </div>
  );
}
