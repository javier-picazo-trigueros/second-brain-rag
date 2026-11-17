import { useId, useState, type KeyboardEvent, type RefObject } from "react";

import { SendIcon, StopIcon } from "./icons";

interface Props {
  onSubmit: (question: string) => void;
  onStop: () => void;
  busy: boolean;
  disabled?: boolean;
  maxLength?: number;
  inputRef?: RefObject<HTMLTextAreaElement | null>;
}

export function AskForm({ onSubmit, onStop, busy, disabled = false, maxLength = 4000, inputRef }: Props) {
  const [value, setValue] = useState("");
  const hintId = useId();
  const trimmed = value.trim();

  function submit() {
    if (busy || disabled || trimmed === "") return;
    onSubmit(trimmed);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Intro envía; Mayús+Intro, nueva línea; durante una composición IME, Intro confirma el texto.
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    submit();
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="rounded-[22px] border border-border bg-surface p-2 pl-4 shadow-[var(--shadow)] transition-colors duration-150 focus-within:border-accent"
    >
      <label htmlFor="ask-input" className="sr-only">
        Tu pregunta
      </label>
      <textarea
        id="ask-input"
        ref={inputRef}
        value={value}
        rows={2}
        maxLength={maxLength}
        disabled={disabled}
        aria-describedby={hintId}
        placeholder="Pregunta algo sobre tus apuntes…"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        className="block max-h-44 w-full resize-none bg-transparent py-1.5 text-base outline-none placeholder:text-muted"
      />
      <div className="mt-1 flex items-center justify-between gap-3">
        <p id={hintId} className="text-xs text-muted">
          Intro envía · Mayús+Intro nueva línea
          {value.length >= maxLength * 0.8 ? (
            <span className="ml-2 tabular-nums">
              {value.length} / {maxLength}
            </span>
          ) : null}
        </p>
        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Parar"
            title="Parar"
            className="grid h-9 w-9 place-items-center rounded-full border border-border-strong bg-surface hover:bg-surface-2"
          >
            <StopIcon size={14} />
          </button>
        ) : (
          <button
            type="submit"
            disabled={disabled || trimmed === ""}
            aria-label="Enviar"
            title="Enviar"
            className="grid h-9 w-9 place-items-center rounded-full bg-accent text-accent-fg transition-transform duration-150 hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
          >
            <SendIcon size={15} />
          </button>
        )}
      </div>
    </form>
  );
}
