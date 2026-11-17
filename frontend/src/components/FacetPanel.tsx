import { useState } from "react";

import type { FacetValue, Facets } from "../lib/api";
import { filtersActive, toggleValue, type Filters } from "../lib/search";

interface Props {
  facets: Facets;
  filters: Filters;
  onChange: (filters: Filters) => void;
}

const VISIBLE_TAGS = 12;

function Group({
  legend,
  values,
  selected,
  onToggle,
  limit,
}: {
  legend: string;
  values: FacetValue[];
  selected: string[];
  onToggle: (value: string) => void;
  limit?: number;
}) {
  const [all, setAll] = useState(false);
  if (values.length === 0) return null;

  const first = limit === undefined || all ? values : values.slice(0, limit);
  // Un valor marcado se ve siempre, aunque quede más allá del límite.
  const shown = limit === undefined || all ? first : [...first, ...values.slice(limit).filter((v) => selected.includes(v.value))];
  const hidden = values.length - shown.length;

  return (
    <fieldset className="min-w-0">
      <legend className="mb-1.5 text-sm font-semibold">{legend}</legend>
      <ul className="space-y-0.5">
        {shown.map((facet) => (
          <li key={facet.value}>
            <label className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-1 text-sm hover:bg-surface-2">
              <input
                type="checkbox"
                checked={selected.includes(facet.value)}
                onChange={() => onToggle(facet.value)}
                className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent)]"
              />{" "}
              <span className="min-w-0 break-words">{facet.value}</span>{" "}
              <span className="ml-auto shrink-0 tabular-nums text-muted">({facet.count})</span>
            </label>
          </li>
        ))}
      </ul>
      {limit !== undefined && (hidden > 0 || all) ? (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className="mt-1 rounded-md px-1 py-0.5 text-sm text-muted hover:bg-surface-2 hover:text-text"
        >
          {all ? "Ver menos" : `Ver más (${hidden})`}
        </button>
      ) : null}
    </fieldset>
  );
}

/** Facetas de la búsqueda: casillas con su recuento. O dentro de cada grupo, Y entre grupos. */
export function FacetPanel({ facets, filters, onChange }: Props) {
  return (
    <div className="space-y-5">
      <Group
        legend="Asignatura"
        values={facets.asignaturas}
        selected={filters.asignaturas}
        onToggle={(v) => onChange({ ...filters, asignaturas: toggleValue(filters.asignaturas, v) })}
      />
      <Group
        legend="Curso"
        values={facets.cursos}
        selected={filters.cursos}
        onToggle={(v) => onChange({ ...filters, cursos: toggleValue(filters.cursos, v) })}
      />
      <Group
        legend="Etiquetas"
        values={facets.tags}
        selected={filters.tags}
        limit={VISIBLE_TAGS}
        onToggle={(v) => onChange({ ...filters, tags: toggleValue(filters.tags, v) })}
      />
      {filtersActive(filters) ? (
        <button
          type="button"
          onClick={() => onChange({ asignaturas: [], cursos: [], tags: [] })}
          className="rounded-md border border-border-strong px-3 py-1.5 text-sm hover:bg-surface-2"
        >
          Quitar los filtros
        </button>
      ) : null}
    </div>
  );
}
