"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { EditorMarca } from "@/components/marca/EditorMarca";

export default function AdminMarcaPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  return (
    <div className="flex flex-col gap-4">
      <Link href="/admin/brands" className="back-link self-start text-sm">
        ← Marcas
      </Link>
      <EditorMarca marcaId={id} admin aoExcluir={() => router.replace("/admin/brands")} />
    </div>
  );
}
