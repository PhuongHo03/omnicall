import type { Meeting, MeetingAsset } from "../types/meetingTypes";

export function isUploadableMeeting(meeting: Meeting, asset: MeetingAsset | null): boolean {
  return meeting.status === "DRAFT" && asset === null;
}

export function isProcessableMeeting(meeting: Meeting, asset: MeetingAsset | null): boolean {
  if (!asset) {
    return false;
  }
  return meeting.status === "UPLOADED" || meeting.status === "FAILED";
}

export function isProcessingMeeting(meeting: Meeting | null): boolean {
  return meeting?.status === "QUEUED" || meeting?.status === "PROCESSING";
}

export function isAudioAsset(asset: MeetingAsset | null): boolean {
  return asset?.contentType.startsWith("audio/") === true;
}

export function isPlayableAsset(asset: MeetingAsset | null): boolean {
  return asset?.contentType.startsWith("audio/") === true || asset?.contentType.startsWith("video/") === true;
}
