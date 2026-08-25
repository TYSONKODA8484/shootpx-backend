"use client";
import type { FieldConfig } from "@/lib/types";

interface FieldInputProps {
  field: FieldConfig;
  value: unknown;
  onChange: (value: unknown) => void;
}

export function FieldInput({ field, value, onChange }: FieldInputProps) {
  const disabled = !field.editable;
  const base = "w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-slate-100 disabled:opacity-50";

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
      <textarea
        className={`${base} font-mono text-xs`}
        rows={4}
        disabled={disabled}
        value={value ? JSON.stringify(value, null, 2) : ""}
        onChange={(e) => {
          try {
            onChange(e.target.value ? JSON.parse(e.target.value) : null);
          } catch {
            // leave the last valid parsed value in place until the JSON is valid again
          }
        }}
      />
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
