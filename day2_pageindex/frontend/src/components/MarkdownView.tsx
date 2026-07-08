import React, { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

interface MarkdownViewProps {
  content: string;
  className?: string;
}

const MarkdownView: React.FC<MarkdownViewProps> = ({ content, className }) => {
  const remarkPlugins = useMemo(() => [remarkGfm, remarkMath], []);
  const rehypePlugins = useMemo(
    () => [[rehypeKatex, { throwOnError: false }]] as any,
    []
  );

  return (
    <div className={`md-body ${className || ""}`}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={{
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
          table: ({ node, ...props }) => (
            <div className="w-full">
              <table {...props} />
            </div>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default memo(MarkdownView);
