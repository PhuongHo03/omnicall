import { useCallback, useEffect, useState } from "react";
import { EmptyState } from "../../../shared/components/EmptyState";

import { useSidebarSlot } from "../../../shared/layouts/SidebarContext";
import { PlaybackDrawer } from "../components/PlaybackDrawer";
import { ResultDrawer } from "../components/ResultDrawer";
import { MeetingActionPanel } from "../components/MeetingActionPanel";
import { MeetingChatPanel } from "../components/MeetingChatPanel";
import { MeetingList } from "../components/MeetingList";
import { MeetingProgressBar } from "../components/MeetingProgressBar";
import { useMeetingWorkspace } from "../hooks/useMeetingWorkspace";
import type { MeetingChatCitation, PlaybackSeekRequest } from "../types/meetingTypes";

type MeetingsScreenProps = {
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

  const { setExtraContent, setOnCreateMeeting } = useSidebarSlot();

  useEffect(() => {
    setOnCreateMeeting(() => workspace.createNewMeeting);
    return () => setOnCreateMeeting(null);
  }, [workspace.createNewMeeting, setOnCreateMeeting]);

  useEffect(() => {
    setExtraContent(
      <MeetingList
        disabled={workspace.isLoading}
        meetings={workspace.meetings}
        selectedMeetingId={workspace.selectedMeetingId}
        onCreate={workspace.createNewMeeting}
        onSelect={workspace.setSelectedMeetingId}
      />
    );
    return () => setExtraContent(null);
  }, [workspace.isLoading, workspace.meetings, workspace.selectedMeetingId, workspace.createNewMeeting, workspace.setSelectedMeetingId, setExtraContent]);

  if (!workspace.selectedMeeting) {
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

    const messageByStatus = {
      DRAFT: "Tải tệp âm thanh để bắt đầu",
      UPLOADED: "Tệp đã tải lên, nhấn Process để bắt đầu",
      FAILED: "Có lỗi xảy ra, vui lòng thử lại",
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
          isUploading={workspace.isLoading}
          isRecording={workspace.isRecording}
          selectedMeeting={workspace.selectedMeeting}
          onDeleteMeeting={workspace.deleteSelectedMeeting}
          onFileUpload={workspace.uploadFile}
          onOpenPlayback={openPlaybackDrawer}
          onProcess={workspace.queueProcessing}
          onRefreshStatus={workspace.refreshStatus}
          onRefreshHistory={workspace.refreshChatHistory}
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
          isOpen={isPlaybackDrawerOpen}
          asset={workspace.lastAsset}
          playbackUrl={workspace.assetPlaybackUrl}
          transcriptEntries={workspace.transcriptEntries}
          onDownload={workspace.downloadAsset}
          onClose={closePlaybackDrawer}
          seekRequest={seekRequest}
        />
      </div>
    </div>
  );
}
