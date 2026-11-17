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
import { citedSources } from "../lib/answer";

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
    <article id={`pregunta-${index}`} className="msg-enter scroll-mt-4 space-y-5">
      <p className="ml-auto w-fit max-w-[85%] whitespace-pre-wrap rounded-[18px_18px_6px_18px] bg-accent-soft px-4 py-2.5 text-text">
        {turn.question}
      </p>

      {turn.status === "waiting" || turn.status === "streaming" ? (
        <div className="space-y-3">
          <p role="status" className="flex items-center gap-2 text-sm text-muted">
            <span className="typing" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            {turn.status === "waiting" ? "Buscando en tus apuntes…" : "Redactando la respuesta…"}
          </p>
          {turn.text === "" ? (
            <div aria-hidden="true" className="space-y-2.5">
              <div className="skeleton h-3 w-4/5" />
              <div className="skeleton h-3 w-3/5" />
            </div>
          ) : null}
        </div>
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
      {done && !notFound ? (
        <SourceCards sources={turn.sources} cited={citedSources(turn.text, turn.fragments)} onOpen={open} />
      ) : null}
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
    <div className="relative flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto scroll-smooth">
        <div className="mx-auto flex max-w-[720px] flex-col gap-9 px-4 pb-52 pt-8 sm:px-5">
          {turns.length > 0 ? <h1 className="sr-only">Preguntar</h1> : null}
          {turns.length === 0 ? (
            <section className="py-10">
              <h1 className="text-2xl font-semibold tracking-tight">Pregunta a tus apuntes</h1>
              <p className="mt-2 text-muted">
                Respondo solo con lo que hay en tu vault y cito las notas de las que sale cada dato.
              </p>
              <ul className="mt-6 flex flex-wrap gap-2">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      type="button"
                      onClick={() => ask(example)}
                      className="rounded-full border border-border bg-surface px-3.5 py-2 text-left text-sm transition-colors hover:border-border-strong hover:bg-surface-2"
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
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-bg from-60% to-[var(--fade)] px-3 pb-3 pt-9 sm:px-5">
        <div className="pointer-events-auto mx-auto max-w-[720px]">
          <AskForm onSubmit={ask} onStop={stop} busy={busy} inputRef={inputRef} />
          <p className="mt-2 text-center text-xs text-muted">
            Cada pregunta se responde de forma independiente: no recuerdo lo que preguntaste antes.
          </p>
        </div>
      </div>
    </div>
  );
}
