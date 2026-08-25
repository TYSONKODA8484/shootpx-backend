"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { EntityConfig, PaginatedResponse } from "@/lib/types";

export default function EntityListPage() {
  const params = useParams<{ entity: string }>();
  const router = useRouter();
  const [config, setConfig] = useState<EntityConfig | null>(null);
  const [data, setData] = useState<PaginatedResponse | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const load = useCallback(() => {
    api.entities().then((all) => {
      setConfig(all.find((e) => e.name === params.entity) ?? null);
    });
    api
      .list(params.entity, page, search)
      .then(setData)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) router.push("/login");
      });
  }, [params.entity, page, search, router]);

  useEffect(() => {
    setPage(1);
  }, [params.entity]);

  useEffect(() => {
    load();
  }, [load]);

  if (!config || !data) return <p className="text-slate-400">Loading...</p>;

  const columns = config.fields.map((f) => f.name);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{config.label}</h1>
        {config.allow_create && (
          <Link href={`/${config.name}/new`} className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white">
            + New
          </Link>
        )}
      </div>
      {config.search_fields.length > 0 && (
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="mb-3 w-64 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-100"
        />
      )}
      <div className="overflow-x-auto rounded border border-slate-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              {columns.map((c) => (
                <th key={c} className="px-3 py-2 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.items.map((row) => (
              <tr
                key={String(row[config.pk_field])}
                onClick={() => router.push(`/${config.name}/${row[config.pk_field]}`)}
                className="cursor-pointer border-t border-slate-800 hover:bg-slate-900"
              >
                {columns.map((c) => (
                  <td key={c} className="max-w-xs truncate px-3 py-2">
                    {formatCell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center gap-3 text-sm text-slate-400">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="disabled:opacity-30">
          Prev
        </button>
        <span>
          Page {data.page} · {data.total} total
        </span>
        <button
          disabled={page * data.page_size >= data.total}
          onClick={() => setPage((p) => p + 1)}
          className="disabled:opacity-30"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
