"use client";

import { useEffect, useState, use } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { TemplateEditor } from "@/components/TemplateEditor";
import { adminApi } from "@/lib/api";
import type { DDTemplate } from "@/lib/types";

export default function TemplateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, status } = useSession();
  const router = useRouter();
  const [template, setTemplate] = useState<DDTemplate | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getTemplate(session.backendToken, id).then(setTemplate).finally(() => setLoading(false));
    }
  }, [session?.backendToken, id]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {loading ? (
          <p className="text-text-tertiary">Loading...</p>
        ) : !template ? (
          <p className="text-text-tertiary">Template not found</p>
        ) : (
          <>
            <h2 className="font-serif text-xl text-text-primary mb-4">{template.name}</h2>
            <TemplateEditor
              initial={{
                name: template.name,
                description: template.description || "",
                industry_slug: template.industry_slug || "",
                stage: template.stage || "",
                dimensions: template.dimensions.map((d) => ({
                  dimension_name: d.dimension_name,
                  weight: d.weight,
                  sort_order: d.sort_order,
                })),
              }}
              onSave={async (data) => {
                await adminApi.updateTemplate(session.backendToken!, id, data);
                const updated = await adminApi.getTemplate(session.backendToken!, id);
                setTemplate(updated);
              }}
              onDelete={async () => {
                try {
                  await adminApi.deleteTemplate(session.backendToken!, id);
                  router.push("/templates");
                } catch {
                  alert("Cannot delete: template is in use by one or more startups.");
                }
              }}
            />
          </>
        )}
      </main>
    </div>
  );
}
