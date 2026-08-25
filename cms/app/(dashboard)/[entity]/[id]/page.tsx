"use client";
import { useParams } from "next/navigation";
import { EntityForm } from "@/lib/EntityForm";

export default function EntityEditPage() {
  const params = useParams<{ entity: string; id: string }>();
  return <EntityForm entity={params.entity} id={params.id} />;
}
