import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

type SidebarContextValue = {
  extraContent: ReactNode | null;
  setExtraContent: (content: ReactNode | null) => void;
  onCreateMeeting: (() => void) | null;
  setOnCreateMeeting: (fn: (() => void) | null) => void;
};

const SidebarContext = createContext<SidebarContextValue>({
  extraContent: null,
  setExtraContent: () => {},
  onCreateMeeting: null,
  setOnCreateMeeting: () => {},
});

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [extraContent, setExtraContentState] = useState<ReactNode | null>(null);
  const [onCreateMeeting, setOnCreateMeetingState] = useState<(() => void) | null>(null);
  const setExtraContent = useCallback((content: ReactNode | null) => setExtraContentState(content), []);
  const setOnCreateMeeting = useCallback((fn: (() => void) | null) => setOnCreateMeetingState(fn), []);
  return (
    <SidebarContext.Provider value={{ extraContent, setExtraContent, onCreateMeeting, setOnCreateMeeting }}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebarSlot() {
  return useContext(SidebarContext);
}
