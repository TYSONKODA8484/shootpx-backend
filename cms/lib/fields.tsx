"use client";
import { useState } from "react";
import type { FieldConfig } from "@/lib/types";

interface FieldInputProps {
  field: FieldConfig;
  value: unknown;
  onChange: (value: unknown) => void;
}

export function FieldInput({ field, value, onChange }: FieldInputProps) {
  const disabled = !field.editable;
  const base = "w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-slate-100 disabled:opacity-50";
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  // Re-derive the editable text from `value` whenever it changes underneath
  // us (e.g. switching rows, or our own onChange committing a new parse),
  // without an effect: adjust state directly during render, the pattern
  // React's docs recommend for "state that mirrors a prop".
  const [lastValue, setLastValue] = useState(value);
  if (field.kind === "json" && value !== lastValue) {
    setLastValue(value);
    setJsonText(value ? JSON.stringify(value, null, 2) : "");
    setJsonError(null);
  }

  if (field.kind === "bool") {
    return (
      <input
        type="checkbox"
        checked={Boolean(value)}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }

  if (field.kind === "enum" && field.enum_values) {
    return (
      <select
        className={base}
        disabled={disabled}
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">--</option>
        {field.enum_values.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
    );
  }

  if (field.kind === "json") {
    return (
      <>
        <textarea
          className={`${base} font-mono text-xs ${jsonError ? "border-red-500" : ""}`}
          rows={4}
          disabled={disabled}
          value={jsonText}
          onChange={(e) => {
            const next = e.target.value;
            setJsonText(next);
            try {
              onChange(next ? JSON.parse(next) : null);
              setJsonError(null);
            } catch (err) {
              setJsonError(err instanceof Error ? err.message : "Invalid JSON");
            }
          }}
        />
        {jsonError && <p className="mt-1 text-xs text-red-400">{jsonError}</p>}
      </>
    );
  }

  if (field.kind === "int" || field.kind === "float") {
    return (
      <input
        type="number"
        className={base}
        disabled={disabled}
        value={value === null || value === undefined ? "" : (value as number)}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    );
  }

  // string, datetime, fk — plain text. fk shows a hint of what entity it points to.
  return (
    <input
      type="text"
      className={base}
      disabled={disabled}
      placeholder={field.kind === "fk" ? `${field.fk_entity} id` : undefined}
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
