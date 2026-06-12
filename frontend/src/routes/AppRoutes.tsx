import { AppShell } from "../layouts/AppShell";
import { MeetingsScreen } from "../features/meetings/screens/MeetingsScreen";

export function AppRoutes() {
  return (
    <AppShell>
      <MeetingsScreen />
    </AppShell>
  );
}
