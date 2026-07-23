import type { Meeting, MeetingAsset, MeetingFailureCode } from "../types/meetingTypes";

type MeetingFailurePresentation = {
  message: string;
  description: string;
};

export function meetingFailurePresentation(code: MeetingFailureCode | null): MeetingFailurePresentation {
  if (code === "NO_RECOGNIZABLE_SPEECH") {
    return {
      message: "Không phát hiện lời nói rõ ràng",
      description: "Bản ghi vẫn có thể nghe lại hoặc tải xuống. Hãy thử ghi âm lại nếu bạn cần tạo transcript.",
    };
  }
  return {
    message: "Không thể xử lý meeting",
    description: "Đã xảy ra lỗi khi xử lý. Vui lòng thử lại sau.",
  };
}

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
