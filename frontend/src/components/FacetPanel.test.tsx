import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import type { Facets } from "../lib/api";
import { EMPTY_FILTERS } from "../lib/search";
import { FacetPanel } from "./FacetPanel";

const tags = Array.from({ length: 15 }, (_, i) => ({ value: `etiqueta-${i + 1}`, count: 15 - i }));
const facets: Facets = {
  asignaturas: [
    { value: "Redes", count: 4 },
    { value: "Data Mining", count: 2 },
  ],
  cursos: [
    { value: "3º", count: 5 },
    { value: "4º", count: 1 },
  ],
  tags,
};

function setup(props: Partial<React.ComponentProps<typeof FacetPanel>> = {}) {
  const onChange = vi.fn();
  render(<FacetPanel facets={facets} filters={EMPTY_FILTERS} onChange={onChange} {...props} />);
  return { onChange };
}

describe("FacetPanel", () => {
  it("shows a group per facet with a checkbox and its count for every value", () => {
    setup();
    const subjects = screen.getByRole("group", { name: "Asignatura" });
    expect(within(subjects).getByRole("checkbox", { name: "Redes (4)" })).not.toBeChecked();
    expect(within(subjects).getByRole("checkbox", { name: "Data Mining (2)" })).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Curso" })).getByRole("checkbox", { name: "3º (5)" })).toBeInTheDocument();
  });

  it("adds a value to its own facet when ticked", async () => {
    const { onChange } = setup({ filters: { asignaturas: ["Redes"], cursos: [], tags: [] } });
    await userEvent.click(screen.getByRole("checkbox", { name: "Data Mining (2)" }));
    expect(onChange).toHaveBeenCalledWith({ asignaturas: ["Redes", "Data Mining"], cursos: [], tags: [] });
  });

  it("removes a value when unticked", async () => {
    const { onChange } = setup({ filters: { asignaturas: ["Redes"], cursos: ["3º"], tags: [] } });
    const box = screen.getByRole("checkbox", { name: "Redes (4)" });
    expect(box).toBeChecked();
    await userEvent.click(box);
    expect(onChange).toHaveBeenCalledWith({ asignaturas: [], cursos: ["3º"], tags: [] });
  });

  it("shows the twelve most frequent tags and the rest on demand", async () => {
    setup();
    const group = screen.getByRole("group", { name: "Etiquetas" });
    expect(within(group).getAllByRole("checkbox")).toHaveLength(12);
    await userEvent.click(within(group).getByRole("button", { name: "Ver más (3)" }));
    expect(within(group).getAllByRole("checkbox")).toHaveLength(15);
    await userEvent.click(within(group).getByRole("button", { name: "Ver menos" }));
    expect(within(group).getAllByRole("checkbox")).toHaveLength(12);
  });

  it("always shows a ticked tag even if it is beyond the first twelve", () => {
    setup({ filters: { asignaturas: [], cursos: [], tags: ["etiqueta-14"] } });
    expect(screen.getByRole("checkbox", { name: "etiqueta-14 (2)" })).toBeChecked();
  });

  it("clears every filter at once and only offers that when something is on", async () => {
    expect(screen.queryByRole("button", { name: "Quitar los filtros" })).toBeNull();
    const { onChange } = setup({ filters: { asignaturas: ["Redes"], cursos: [], tags: ["x"] } });
    await userEvent.click(screen.getByRole("button", { name: "Quitar los filtros" }));
    expect(onChange).toHaveBeenCalledWith(EMPTY_FILTERS);
  });

  it("leaves out a facet that has no values", () => {
    setup({ facets: { asignaturas: [], cursos: [], tags: [] } });
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(
      <FacetPanel facets={facets} filters={{ asignaturas: ["Redes"], cursos: [], tags: [] }} onChange={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
