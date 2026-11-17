import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { AnswerView } from "../components/AnswerView";
import { AskForm } from "../components/AskForm";
import { ErrorBanner } from "../components/ErrorBanner";
import { NoticeBar } from "../components/NoticeBar";
import { NotFoundCard } from "../components/NotFoundCard";
import { SourceCards } from "../components/SourceCards";
import type { AskState } from "../hooks/askState";
import { useConversation } from "../hooks/conversation";
import { useNotePanel } from "../hooks/notePanel";

const EXAMPLES = [
  "¿Qué es un semáforo y para qué sirve?",
  "¿Cómo funciona el filtrado de paquetes con iptables?",
  "¿Qué diferencia hay entre un proceso y un hilo?",
];

const HIDDEN_WHEN_NOT_FOUND = ["confianza_baja", "sin_citas", "solo_pistas"];

function Turn({ turn, index, focusInput }: { turn: AskState; index: number; focusInput: () => void }) {
  const { open } = useNotePanel();
  const evidence = turn.sources.filter((s) => s.kind === "evidence").length;
  const done = turn.done;
  const notFound = done?.not_found === true;

  return (
    <article id={`pregunta-${index}`} className="scroll-mt-4 space-y-4">
      <p className="ml-auto w-fit max-w-[85%] whitespace-pre-wrap rounded-md bg-accent-soft px-4 py-2 text-text">
        {turn.question}
      </p>

      {turn.status === "waiting" || turn.status === "streaming" ? (
        <p role="status" className="text-sm text-muted">
          {turn.status === "waiting" ? "Buscando en tus apuntes…" : "Redactando la respuesta…"}
        </p>
      ) : null}

      {notFound && done ? (
        <NotFoundCard
          answer={done.answer}
          fragments={turn.fragments}
          evidenceCount={evidence}
          lowConfidence={done.confidence === "baja"}
          onOpenNote={open}
          onRephrase={focusInput}
        />
      ) : turn.text ? (
        <AnswerView
          text={turn.text}
          fragments={turn.fragments}
          streaming={turn.status === "streaming"}
          onOpenNote={open}
        />
      ) : null}

      {turn.status === "stopped" ? <p className="text-sm text-muted">Respuesta detenida</p> : null}
      {turn.status === "error" && turn.error ? <ErrorBanner message={turn.error} /> : null}

      {done ? <NoticeBar done={done} sources={turn.sources} hide={notFound ? HIDDEN_WHEN_NOT_FOUND : []} /> : null}
      {done && !notFound ? <SourceCards sources={turn.sources} onOpen={open} /> : null}
    </article>
  );
}

export function Preguntar() {
  const { turns, busy, ask, stop } = useConversation();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { hash } = useLocation();
  const last = turns[turns.length - 1];

  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView?.({ block: "start" });
  }, [hash]);

  useEffect(() => {
    if (!hash) bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [last?.text, last?.status, turns.length, hash]);

  const focusInput = () => inputRef.current?.focus();

  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col px-4 py-6">
      <div className="flex-1 space-y-10">
        {turns.length === 0 ? (
          <section className="py-10">
            <h1 className="text-2xl font-semibold">Pregunta a tus apuntes</h1>
            <p className="mt-2 text-muted">
              Respondo solo con lo que hay en tu vault y cito las notas de las que sale cada dato.
            </p>
            <ul className="mt-6 flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => ask(example)}
                    className="rounded-full border border-border bg-surface px-3 py-1.5 text-left text-sm hover:border-accent"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          turns.map((turn, index) => <Turn key={index} turn={turn} index={index} focusInput={focusInput} />)
        )}
        <div ref={bottomRef} />
      </div>

      <div className="sticky bottom-0 mt-6 bg-bg pb-2 pt-3">
        <AskForm onSubmit={ask} onStop={stop} busy={busy} inputRef={inputRef} />
        <p className="mt-2 text-xs text-muted">
          Cada pregunta se responde de forma independiente: no recuerdo lo que preguntaste antes.
        </p>
      </div>
    </div>
  );
}
