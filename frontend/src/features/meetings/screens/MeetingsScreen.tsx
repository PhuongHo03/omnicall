import { useCallback, useEffect, useState } from "react";
import { EmptyState } from "../../../shared/components/EmptyState";

import { useSidebarSlot } from "../../../shared/layouts/SidebarContext";
import { PlaybackDrawer } from "../components/PlaybackDrawer";
import { ResultDrawer } from "../components/ResultDrawer";
import { MeetingActionPanel } from "../components/MeetingActionPanel";
import { MeetingChatPanel } from "../components/MeetingChatPanel";
import { MeetingList } from "../components/MeetingList";
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

        {workspace.selectedMeeting.status === "READY" ? (
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
        ) : (
          <EmptyState message="Upload and process a meeting to start chatting." />
        )}

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
