import { useEffect, useRef, useState } from "react";
import { parseMarkdown } from "../utils/markdownParser";

const DEFAULT_SPEED_MS = 16;

/**
 * Parse markdown to HTML and wrap each text character in a span
 * with data-tw attribute for progressive reveal.
 */
function buildFormattedHtml(markdown: string): { html: string; charCount: number } {
  const html = parseMarkdown(markdown);
  let charCount = 0;

  // Replace text between HTML tags with span-wrapped characters
  const result = html.replace(/>([^<]+)</g, (_match, text: string) => {
    let wrapped = "";
    for (let i = 0; i < text.length; i++) {
      const ch = text[i] === " " ? "\u00a0" : text[i]; // preserve spaces
      wrapped += `<span data-tw>${ch}</span>`;
      charCount++;
    }
    return ">" + wrapped + "<";
  });

  return { html: result, charCount };
}

export function useFormattedTypewriter(
  markdown: string,
  enabled: boolean,
  speedMs: number = DEFAULT_SPEED_MS,
) {
  const [counter, setCounter] = useState(enabled ? 0 : -1);
  const [isAnimating, setIsAnimating] = useState(enabled);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { html, charCount } = buildFormattedHtml(markdown);

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
  }, [markdown, enabled, speedMs, charCount]);

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

  return { displayed, isAnimating };
}
