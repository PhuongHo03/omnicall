import { useEffect, type RefObject } from "react";

/**
 * Scroll a container to its bottom when dependencies change.
 */
export function useAutoScroll(
  containerRef: RefObject<HTMLElement | null>,
  deps: unknown[],
) {
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
