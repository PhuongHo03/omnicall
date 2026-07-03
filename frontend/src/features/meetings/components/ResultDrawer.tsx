import { Drawer } from "../../../shared/components/Drawer";
import { MeetingIntelligenceResultPanel } from "./MeetingIntelligenceResultPanel";
import type { MeetingIntelligenceResult } from "../types/meetingTypes";

type ResultDrawerProps = {
  isOpen: boolean;
  result: MeetingIntelligenceResult | null;
  onClose: () => void;
};

export function ResultDrawer({ isOpen, result, onClose }: ResultDrawerProps) {
  return (
    <Drawer isOpen={isOpen} title="Intelligence Result" ariaLabel="Processed JSON result" onClose={onClose}>
      <MeetingIntelligenceResultPanel result={result!} />
    </Drawer>
  );
}
