import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

function normalizeMarkdown(content: string) {
  return content
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, formula) => `\n\n$$${formula}$$\n\n`)
    .replace(/\\\((.*?)\\\)/g, (_, formula) => `$${formula}$`)
    .replace(/([^\n])\s+(#{1,6}\s)/g, "$1\n\n$2");
}

export default function MarkdownContent({
  content,
  compact = false,
}: {
  content: string;
  compact?: boolean;
}) {
  return (
    <div className={`markdown-body ${compact ? "compact" : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer" />
          ),
        }}
      >
        {normalizeMarkdown(content || "暂无内容")}
      </ReactMarkdown>
    </div>
  );
}
