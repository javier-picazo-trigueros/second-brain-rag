import { useMemo } from "react";

import type { FragmentInfo } from "../lib/api";
import { answerToMarkdown } from "../lib/answer";
import { CitationChip } from "./CitationChip";
import { ExternalLink, Markdown, noteComponents } from "./Markdown";

interface Props {
  text: string;
  fragments: FragmentInfo[];
  streaming?: boolean;
  onOpenNote: (path: string, page: number | null) => void;
}

/** Respuesta del modelo: Markdown saneado donde cada cita `[S#]` es un chip. */
export function AnswerView({ text, fragments, streaming = false, onOpenNote }: Props) {
  const { markdown, refs } = useMemo(() => answerToMarkdown(text, fragments), [text, fragments]);

  const components = useMemo(
    () => ({
      ...noteComponents,
      a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
        const index = href?.startsWith("cite:") ? Number(href.slice(5)) : -1;
        const ref = refs[index];
        if (ref) return <CitationChip citation={ref} onOpen={onOpenNote} />;
        return <ExternalLink href={href}>{children}</ExternalLink>;
      },
    }),
    [refs, onOpenNote],
  );

  return (
    <div data-testid="answer" className="reading answer-text" aria-busy={streaming}>
      <Markdown components={components}>{markdown}</Markdown>
      {streaming ? (
        <span
          data-testid="cursor"
          aria-hidden="true"
          className="ml-0.5 inline-block h-4 w-0.5 translate-y-0.5 animate-pulse bg-accent"
        />
      ) : null}
    </div>
  );
}
