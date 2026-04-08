"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { TemplateEditor } from "@/components/TemplateEditor";
import { adminApi } from "@/lib/api";

export default function NewTemplatePage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">New Template</h2>
        <TemplateEditor
          onSave={async (data) => {
            await adminApi.createTemplate(session.backendToken!, data);
            router.push("/templates");
          }}
        />
      </main>
    </div>
  );
}
