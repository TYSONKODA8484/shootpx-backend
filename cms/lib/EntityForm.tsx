"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { FieldInput } from "@/lib/fields";
import type { EntityConfig } from "@/lib/types";

interface EntityFormProps {
  entity: string;
  id?: string; // undefined => create mode
}

export function EntityForm({ entity, id }: EntityFormProps) {
  const router = useRouter();
  const [config, setConfig] = useState<EntityConfig | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.entities().then((all) => {
      const found = all.find((e) => e.name === entity) ?? null;
      setConfig(found);
      if (found && id) {
        api.get(entity, id).then(setValues);
      }
    });
  }, [entity, id]);

  if (!config) return <p className="text-slate-400">Loading...</p>;

  const isCreate = !id;

  async function handleSave() {
    setError(null);
    setSaving(true);
    try {
      if (isCreate) {
        const created = await api.create(entity, values);
        router.push(`/${entity}/${created[config!.pk_field]}`);
      } else {
        await api.update(entity, id!, values);
        router.refresh();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!id || !confirm(`Delete this ${config!.label} row?`)) return;
    setError(null);
    try {
      await api.remove(entity, id);
      router.push(`/${entity}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    }
  }

  return (
    <div className="max-w-xl">
      <h1 className="mb-4 text-xl font-semibold">{isCreate ? `New ${config.label}` : `Edit ${config.label}`}</h1>
      <div className="space-y-3">
        {config.fields.map((f) => {
          // On create, the PK is editable only when the entity requires it
          // to be supplied (pk_provided_on_create); every other locked field
          // stays locked in both modes.
          const isPk = f.name === config.pk_field;
          const locked = isCreate && isPk && config.pk_provided_on_create ? false : !f.editable;
          return (
            <div key={f.name}>
              <label className="mb-1 block text-xs text-slate-400">
                {f.name}
                {locked ? " (read-only)" : ""}
              </label>
              <FieldInput
                field={{ ...f, editable: !locked }}
                value={values[f.name]}
                onChange={(v) => setValues((prev) => ({ ...prev, [f.name]: v }))}
              />
            </div>
          );
        })}
      </div>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      <div className="mt-4 flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save"}
        </button>
        {!isCreate && config.allow_delete && (
          <button onClick={handleDelete} className="rounded bg-red-600 px-3 py-1.5 text-sm text-white">
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
