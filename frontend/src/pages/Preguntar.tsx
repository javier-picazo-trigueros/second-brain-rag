import { useEffect, useRef, useState } from "react";

import { AnswerView } from "../components/AnswerView";
import { AskForm } from "../components/AskForm";
import { ErrorBanner } from "../components/ErrorBanner";
import { NoticeBar } from "../components/NoticeBar";
import { NotFoundCard } from "../components/NotFoundCard";
import { SourceCards } from "../components/SourceCards";
import type { AskState } from "../hooks/askState";
import { useNotePanel } from "../hooks/notePanel";
import { useSession } from "../hooks/session";
import { useAsk } from "../hooks/useAsk";

const EXAMPLES = [
  "¿Qué es un semáforo y para qué sirve?",
  "¿Cómo funciona el filtrado de paquetes con iptables?",
  "¿Qué diferencia hay entre un proceso y un hilo?",
];

const HIDDEN_WHEN_NOT_FOUND = ["confianza_baja", "sin_citas", "solo_pistas"];

function Turn({ turn, focusInput }: { turn: AskState; focusInput: () => void }) {
  const { open } = useNotePanel();
  const evidence = turn.sources.filter((s) => s.kind === "evidence").length;
  const done = turn.done;
  const notFound = done?.not_found === true;

  return (
    <article className="space-y-4">
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
          sources={turn.sources}
          evidenceCount={evidence}
          lowConfidence={done.confidence === "baja"}
          onOpenNote={open}
          onRephrase={focusInput}
        />
      ) : turn.text ? (
        <AnswerView text={turn.text} sources={turn.sources} streaming={turn.status === "streaming"} onOpenNote={open} />
      ) : null}

      {turn.status === "stopped" ? <p className="text-sm text-muted">Respuesta detenida</p> : null}
      {turn.status === "error" && turn.error ? <ErrorBanner message={turn.error} /> : null}

      {done ? <NoticeBar done={done} sources={turn.sources} hide={notFound ? HIDDEN_WHEN_NOT_FOUND : []} /> : null}
      {done && !notFound ? <SourceCards sources={turn.sources} onOpen={open} /> : null}
    </article>
  );
}

export function Preguntar() {
  const { state, ask, stop } = useAsk();
  const { record } = useSession();
  const [history, setHistory] = useState<AskState[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recorded = useRef<unknown>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const busy = state.status === "waiting" || state.status === "streaming";

  useEffect(() => {
    if (state.done && recorded.current !== state.done) {
      recorded.current = state.done;
      record(state.done);
    }
  }, [state.done, record]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [state.text, state.status]);

  function submit(question: string) {
    if (state.status !== "idle") setHistory((prev) => [...prev, state]);
    void ask(question);
  }

  const focusInput = () => inputRef.current?.focus();
  const empty = history.length === 0 && state.status === "idle";

  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col px-4 py-6">
      <div className="flex-1 space-y-10">
        {empty ? (
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
                    onClick={() => submit(example)}
                    className="rounded-full border border-border bg-surface px-3 py-1.5 text-left text-sm hover:border-accent"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <>
            {history.map((turn, index) => (
              <Turn key={index} turn={turn} focusInput={focusInput} />
            ))}
            <Turn turn={state} focusInput={focusInput} />
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="sticky bottom-0 mt-6 bg-bg pb-2 pt-3">
        <AskForm onSubmit={submit} onStop={stop} busy={busy} inputRef={inputRef} />
        <p className="mt-2 text-xs text-muted">
          Cada pregunta se responde de forma independiente: no recuerdo lo que preguntaste antes.
        </p>
      </div>
    </div>
  );
}
