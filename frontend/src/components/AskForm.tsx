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
      className="rounded-md border border-border-strong bg-surface p-2 focus-within:border-accent"
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
        className="block max-h-48 w-full resize-none bg-transparent px-2 py-1 text-base outline-none placeholder:text-muted"
      />
      <div className="mt-1 flex items-center justify-between gap-3">
        <p id={hintId} className="px-2 text-xs text-muted">
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
            className="inline-flex items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
          >
            <StopIcon size={14} />
            Parar
          </button>
        ) : (
          <button
            type="submit"
            disabled={disabled || trimmed === ""}
            className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg disabled:cursor-not-allowed disabled:opacity-50"
          >
            <SendIcon size={14} />
            Enviar
          </button>
        )}
      </div>
    </form>
  );
}
