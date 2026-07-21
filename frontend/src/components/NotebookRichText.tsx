"use client";

import katex from "katex";
import type { ReactNode } from "react";

type Block =
  | { kind: "paragraph"; text: string }
  | { kind: "heading"; level: number; text: string }
  | { kind: "unordered" | "ordered"; items: string[] }
  | { kind: "code"; text: string }
  | { kind: "math"; text: string };

function mathMarkup(expression: string, displayMode: boolean) {
  const cleaned = expression.trim().replace(/^\\\[|\\\]$/g, "").replace(/^\$\$|\$\$$/g, "").trim();
  try {
    return katex.renderToString(cleaned, {
      displayMode,
      output: "htmlAndMathml",
      throwOnError: false,
      strict: "ignore",
      trust: false,
    });
  } catch {
    return null;
  }
}

export function NotebookMath({ expression, display = false }: { expression: string; display?: boolean }) {
  const markup = mathMarkup(expression, display);
  if (!markup) return <code className={display ? "nlm-math-fallback nlm-math-block" : "nlm-math-fallback"}>{expression}</code>;
  return display
    ? <div className="nlm-math-block" dangerouslySetInnerHTML={{ __html: markup }} />
    : <span className="nlm-math-inline" dangerouslySetInnerHTML={{ __html: markup }} />;
}

function inlineContent(text: string): ReactNode[] {
  const pattern = /(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$(?!\$)[^$\n]+?\$|`[^`\n]+`|\*\*[^*\n]+?\*\*|\*[^*\n]+?\*)/g;
  const result: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > cursor) result.push(<span key={`text-${key++}`}>{text.slice(cursor, match.index)}</span>);
    const token = match[0];
    if (token.startsWith("\\[")) {
      result.push(<NotebookMath key={`math-${key++}`} expression={token.slice(2, -2)} display />);
    } else if (token.startsWith("\\(")) {
      result.push(<NotebookMath key={`math-${key++}`} expression={token.slice(2, -2)} />);
    } else if (token.startsWith("$")) {
      result.push(<NotebookMath key={`math-${key++}`} expression={token.slice(1, -1)} />);
    } else if (token.startsWith("`")) {
      result.push(<code key={`code-${key++}`}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      result.push(<strong key={`strong-${key++}`}>{inlineContent(token.slice(2, -2))}</strong>);
    } else {
      result.push(<em key={`em-${key++}`}>{inlineContent(token.slice(1, -1))}</em>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) result.push(<span key={`text-${key}`}>{text.slice(cursor)}</span>);
  return result;
}

function InlineText({ text }: { text: string }) {
  const lines = text.split("\n");
  return <>{lines.map((line, index) => <span key={`line-${index}`}>{index ? <br /> : null}{inlineContent(line)}</span>)}</>;
}

function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { kind: "unordered" | "ordered"; items: string[] } | null = null;
  let code: string[] | null = null;
  let math: string[] | null = null;
  let mathEnd = "";

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (code) {
      if (/^```/.test(trimmed)) {
        blocks.push({ kind: "code", text: code.join("\n") });
        code = null;
      } else code.push(line);
      continue;
    }
    if (math) {
      math.push(line);
      if (trimmed === mathEnd) {
        blocks.push({ kind: "math", text: math.slice(0, -1).join("\n") });
        math = null;
        mathEnd = "";
      }
      continue;
    }
    if (/^```/.test(trimmed)) {
      flushParagraph(); flushList(); code = [];
      continue;
    }
    if (trimmed === "$$" || trimmed === "\\[") {
      flushParagraph(); flushList(); math = []; mathEnd = trimmed === "$$" ? "$$" : "\\]";
      continue;
    }
    const singleMath = trimmed.match(/^\$\$(.+)\$\$$/);
    if (singleMath) {
      flushParagraph(); flushList(); blocks.push({ kind: "math", text: singleMath[1] });
      continue;
    }
    const singleBracketMath = trimmed.match(/^\\\[([\s\S]+)\\\]$/);
    if (singleBracketMath) {
      flushParagraph(); flushList(); blocks.push({ kind: "math", text: singleBracketMath[1] });
      continue;
    }
    const environment = trimmed.match(/^\\begin\{([^}]+)\}/);
    if (environment) {
      flushParagraph(); flushList(); math = [line]; mathEnd = `\\end{${environment[1]}}`;
      continue;
    }
    if (!trimmed) {
      flushParagraph(); flushList();
      continue;
    }
    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph(); flushList(); blocks.push({ kind: "heading", level: Math.min(3, heading[1].length), text: heading[2] });
      continue;
    }
    const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const kind = unordered ? "unordered" : "ordered";
      if (!list || list.kind !== kind) { flushList(); list = { kind, items: [] }; }
      list.items.push((unordered || ordered)?.[1] || "");
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  if (code) blocks.push({ kind: "code", text: code.join("\n") });
  if (math) blocks.push({ kind: "math", text: math.join("\n") });
  flushParagraph(); flushList();
  return blocks;
}

export default function NotebookRichText({ content, className = "" }: { content: string; className?: string }) {
  const blocks = parseBlocks(content || "");
  return <div className={`nlm-rich-text ${className}`.trim()}>
    {blocks.length ? blocks.map((block, index) => {
      if (block.kind === "math") return <NotebookMath key={`block-${index}`} expression={block.text} display />;
      if (block.kind === "code") return <pre key={`block-${index}`}><code>{block.text}</code></pre>;
      if (block.kind === "heading") {
        const Heading = block.level === 1 ? "h2" : block.level === 2 ? "h3" : "h4";
        return <Heading key={`block-${index}`}><InlineText text={block.text} /></Heading>;
      }
      if (block.kind === "unordered" || block.kind === "ordered") {
        const List = block.kind === "unordered" ? "ul" : "ol";
        return <List key={`block-${index}`}>{block.items.map((item, itemIndex) => <li key={`item-${itemIndex}`}><InlineText text={item} /></li>)}</List>;
      }
      if (block.kind === "paragraph") return <p key={`block-${index}`}><InlineText text={block.text} /></p>;
      return null;
    }) : <p />}
  </div>;
}
