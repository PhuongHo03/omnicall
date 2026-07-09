import { useEffect, useRef, useState } from "react";
import { parseMarkdown } from "../utils/markdownParser";

const DEFAULT_SPEED_MS = 16;

/**
 * Parse markdown to HTML and wrap each text character in a span
 * with data-tw attribute for progressive reveal.
 */
function buildFormattedHtml(markdown: string = ""): { html: string; charCount: number } {
  const html = parseMarkdown(markdown);
  let charCount = 0;

  // Replace text between HTML tags with span-wrapped characters
  // Also handle text not wrapped in tags (at start/end or standalone)
  const result = html.replace(/>([^<]+)</g, (_match, text: string) => {
    let wrapped = "";
    for (let i = 0; i < text.length; i++) {
      const ch = text[i] === " " ? "\u00a0" : text[i]; // preserve spaces
      wrapped += `<span data-tw>${ch}</span>`;
      charCount++;
    }
    return ">" + wrapped + "<";
  });

  // Handle text not wrapped in tags (e.g., standalone text without parent tags)
  // This regex matches text that is not inside < > tags
  const finalResult = result.replace(/^([^<]+(?:<[^>]*>[^<]*<\/[^>]*>[^<]*)*)$/, (match) => {
    // Only process if there are no <span data-tw> tags already
    if (match.includes("data-tw")) return match;
    
    let wrapped = "";
    for (let i = 0; i < match.length; i++) {
      const ch = match[i];
      if (ch === "<") {
        // Find the closing tag and add it as-is
        const closeIndex = match.indexOf(">", i);
        if (closeIndex !== -1) {
          wrapped += match.slice(i, closeIndex + 1);
          i = closeIndex;
          continue;
        }
      }
      if (ch === " ") {
        wrapped += "\u00a0";
      } else {
        wrapped += `<span data-tw>${ch}</span>`;
      }
      charCount++;
    }
    return wrapped;
  });

  return { html: finalResult, charCount };
}

export function useFormattedTypewriter(
  markdown: string = "",
  enabled: boolean,
  speedMs: number = DEFAULT_SPEED_MS,
) {
  const safeMarkdown = markdown ?? "";
  const [counter, setCounter] = useState(enabled ? 0 : -1);
  const [isAnimating, setIsAnimating] = useState(enabled);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { html, charCount } = buildFormattedHtml(safeMarkdown);

  useEffect(() => {
    if (!enabled) {
      setCounter(-1);
      setIsAnimating(false);
      return;
    }

    setCounter(0);
    setIsAnimating(true);
    let current = 0;

    timerRef.current = setInterval(() => {
      current++;
      if (current >= charCount) {
        setCounter(-1); // -1 = show all
        setIsAnimating(false);
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }
      setCounter(current);
    }, speedMs);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [safeMarkdown, enabled, speedMs, charCount]);

  // Build display HTML: hide chars beyond counter
  let displayed: string;
  if (counter === -1) {
    // Show all — remove data-tw spans, keep just text
    displayed = html.replace(/<span data-tw>(.*?)<\/span>/g, "$1");
  } else {
    let seen = 0;
    displayed = html.replace(/<span data-tw>(.*?)<\/span>/g, (_match, ch: string) => {
      seen++;
      if (seen <= counter) {
        return ch;
      }
      return `<span style="opacity:0">${ch}</span>`;
    });
  }

  // Build visible HTML (only chars with opacity:1) for caret positioning
  let visibleHtml: string;
  if (counter === -1) {
    visibleHtml = displayed;
  } else {
    let seenForVisible = 0;
    visibleHtml = html.replace(/<span data-tw>(.*?)<\/span>/g, (_match, ch: string) => {
      seenForVisible++;
      if (seenForVisible <= counter) {
        return ch;
      }
      return "";
    });
  }

  return { displayed, visibleHtml, isAnimating };
}
