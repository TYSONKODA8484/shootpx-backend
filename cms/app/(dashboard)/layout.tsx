"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { EntityConfig } from "@/lib/types";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [entities, setEntities] = useState<EntityConfig[] | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    api
      .entities()
      .then(setEntities)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
        }
      });
  }, [router]);

  if (!entities) {
    return <div className="p-6 text-slate-400">Loading...</div>;
  }

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <nav className="w-56 shrink-0 border-r border-slate-800 p-4">
        <Link href="/" className="mb-4 block font-semibold">
          Overview
        </Link>
        <ul className="space-y-1">
          {entities.map((e) => (
            <li key={e.name}>
              <Link
                href={`/${e.name}`}
                className={`block rounded px-2 py-1 text-sm hover:bg-slate-800 ${
                  pathname?.startsWith(`/${e.name}`) ? "bg-slate-800" : ""
                }`}
              >
                {e.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
