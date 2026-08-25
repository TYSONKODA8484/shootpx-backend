"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Stats } from "@/lib/types";

export default function OverviewPage() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    api.stats().then(setStats).catch(() => {});
  }, []);

  if (!stats) return <p className="text-slate-400">Loading stats...</p>;

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Overview</h1>
      <div className="grid grid-cols-3 gap-4">
        <StatTile label="Total users" value={stats.total_users} />
        <StatTile label="Total teams" value={stats.total_teams} />
        <StatTile label="Total credit balance" value={stats.total_credit_balance} />
      </div>
      <h2 className="mb-2 mt-6 text-sm font-medium text-slate-400">Subscriptions by plan</h2>
      <ul className="space-y-1">
        {Object.entries(stats.subscriptions_by_plan).map(([plan, count]) => (
          <li key={plan} className="text-sm">
            {plan}: {count}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
    </div>
  );
}
