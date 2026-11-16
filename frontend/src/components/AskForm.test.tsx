import { createEvent, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import { AskForm } from "./AskForm";

function setup(props: Partial<React.ComponentProps<typeof AskForm>> = {}) {
  const onSubmit = vi.fn();
  const onStop = vi.fn();
  render(<AskForm onSubmit={onSubmit} onStop={onStop} busy={false} {...props} />);
  return { onSubmit, onStop, box: screen.getByRole("textbox", { name: "Tu pregunta" }) };
}

describe("AskForm", () => {
  it("has an accessible label and a disabled send button while empty", () => {
    setup();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeDisabled();
  });

  it("submits the trimmed question on Enter and clears the box", async () => {
    const { onSubmit, box } = setup();
    await userEvent.type(box, "  ¿Qué es un semáforo?  {Enter}");
    expect(onSubmit).toHaveBeenCalledWith("¿Qué es un semáforo?");
    expect(box).toHaveValue("");
  });

  it("submits with the button", async () => {
    const { onSubmit, box } = setup();
    await userEvent.type(box, "hola");
    await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(onSubmit).toHaveBeenCalledWith("hola");
  });

  it("inserts a new line on Shift+Enter instead of submitting", async () => {
    const { onSubmit, box } = setup();
    await userEvent.type(box, "línea 1{Shift>}{Enter}{/Shift}línea 2");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(box).toHaveValue("línea 1\nlínea 2");
  });

  it("ignores Enter on an empty or whitespace-only question", async () => {
    const { onSubmit, box } = setup();
    await userEvent.type(box, "   {Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("does not submit while an IME composition is in progress", () => {
    const { onSubmit, box } = setup();
    fireEvent.change(box, { target: { value: "にほん" } });
    const event = createEvent.keyDown(box, { key: "Enter", isComposing: true });
    fireEvent(box, event);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("turns the send button into Stop while answering", async () => {
    const { onStop } = setup({ busy: true });
    expect(screen.queryByRole("button", { name: "Enviar" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Parar" }));
    expect(onStop).toHaveBeenCalled();
  });

  it("does not submit while busy, but keeps what was typed", async () => {
    const { onSubmit, box } = setup({ busy: true });
    await userEvent.type(box, "siguiente{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(box).toHaveValue("siguiente");
  });

  it("can be disabled entirely", () => {
    const { box } = setup({ disabled: true });
    expect(box).toBeDisabled();
  });

  it("warns when approaching the length limit", async () => {
    const { box } = setup({ maxLength: 20 });
    fireEvent.change(box, { target: { value: "x".repeat(18) } });
    expect(screen.getByText("18 / 20")).toBeInTheDocument();
  });

  it("does not show the counter for short questions", async () => {
    const { box } = setup({ maxLength: 4000 });
    await userEvent.type(box, "corta");
    expect(screen.queryByText(/ \/ 4000/)).toBeNull();
  });

  it("can be focused from outside", () => {
    const ref = { current: null as HTMLTextAreaElement | null };
    render(<AskForm onSubmit={() => {}} onStop={() => {}} busy={false} inputRef={ref} />);
    expect(ref.current).toBe(screen.getByRole("textbox"));
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<AskForm onSubmit={() => {}} onStop={() => {}} busy={false} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
