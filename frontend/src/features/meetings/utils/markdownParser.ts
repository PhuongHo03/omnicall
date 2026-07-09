/**
 * Lightweight markdown → HTML parser for LLM chat responses.
 * Handles: **bold**, *italic*, `code`, \n line breaks, * bullet lists.
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function parseInlineFormatting(text: string): string {
  let result = "";
  let i = 0;

  while (i < text.length) {
    // **bold**
    if (text[i] === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end !== -1) {
        const inner = text.slice(i + 2, end);
        result += "<strong>" + parseInlineFormatting(inner) + "</strong>";
        i = end + 2;
        continue;
      }
    }

    // *italic*
    if (text[i] === "*") {
      const end = text.indexOf("*", i + 1);
      if (end !== -1 && end > i + 1) {
        const inner = text.slice(i + 1, end);
        result += "<em>" + parseInlineFormatting(inner) + "</em>";
        i = end + 1;
        continue;
      }
    }

    // `code`
    if (text[i] === "`") {
      const end = text.indexOf("`", i + 1);
      if (end !== -1) {
        const code = escapeHtml(text.slice(i + 1, end));
        result += "<code>" + code + "</code>";
        i = end + 1;
        continue;
      }
    }

    result += escapeHtml(text[i]);
    i++;
  }

  return result;
}

export function parseMarkdown(markdown: string = ""): string {
  const lines = markdown.split("\n");
  const blocks: string[] = [];
  let inList = false;

  for (const line of lines) {
    const trimmed = line.trim();

    // Empty line → close list, add break
    if (trimmed === "") {
      if (inList) {
        blocks.push("</ul>");
        inList = false;
      }
      blocks.push("<br>");
      continue;
    }

    // Bullet list item: * text or - text
    const bulletMatch = trimmed.match(/^[*-]\s+(.+)/);
    if (bulletMatch) {
      if (!inList) {
        blocks.push("<ul>");
        inList = true;
      }
      blocks.push("<li>" + parseInlineFormatting(bulletMatch[1]) + "</li>");
      continue;
    }

    // Regular text line
    if (inList) {
      blocks.push("</ul>");
      inList = false;
    }
    blocks.push(parseInlineFormatting(trimmed));
  }

  if (inList) {
    blocks.push("</ul>");
  }

  return blocks.join("");
}
