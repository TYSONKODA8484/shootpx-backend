"use client";
import { useParams } from "next/navigation";
import { EntityForm } from "@/lib/EntityForm";

export default function EntityCreatePage() {
  const params = useParams<{ entity: string }>();
  return <EntityForm entity={params.entity} />;
}
