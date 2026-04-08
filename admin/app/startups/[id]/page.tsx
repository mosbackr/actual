"use client";

import { useEffect, useState, use } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StartupEditor } from "@/components/StartupEditor";
import { DimensionManager } from "@/components/DimensionManager";
import { ExpertPicker } from "@/components/ExpertPicker";
import { adminApi } from "@/lib/api";
import type { PipelineStartup, DDTemplate, Dimension, ApprovedExpert, Assignment } from "@/lib/types";

export default function StartupDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, status } = useSession();
  const [startup, setStartup] = useState<PipelineStartup | null>(null);
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [templates, setTemplates] = useState<DDTemplate[]>([]);
  const [experts, setExperts] = useState<ApprovedExpert[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.backendToken, id]);

  async function loadAll() {
    if (!session?.backendToken) return;
    setLoading(true);
    try {
      const [pipeline, dims, tmpls, exps, assigns] = await Promise.all([
        adminApi.getPipeline(session.backendToken),
        adminApi.getDimensions(session.backendToken, id),
        adminApi.getTemplates(session.backendToken),
        adminApi.getApprovedExperts(session.backendToken),
        adminApi.getAssignments(session.backendToken, id),
      ]);
      setStartup(pipeline.find((s) => s.id === id) || null);
      setDimensions(dims);
      setTemplates(tmpls);
      setExperts(exps);
      setAssignments(assigns);
    } finally {
      setLoading(false);
    }
  }

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {loading || !startup ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-8">
            <h2 className="text-xl font-bold">{startup.name}</h2>

            <section>
              <h3 className="text-lg font-medium mb-3">Edit Startup</h3>
              <StartupEditor
                initial={{
                  name: startup.name,
                  description: startup.description,
                  website_url: null,
                  stage: startup.stage,
                  status: startup.status,
                  location_city: null,
                  location_state: null,
                  location_country: "US",
                }}
                onSave={async (data) => {
                  await adminApi.updateStartup(session.backendToken!, id, data);
                  loadAll();
                }}
              />
            </section>

            <hr className="border-gray-800" />

            <section>
              <DimensionManager
                dimensions={dimensions}
                templates={templates}
                onApplyTemplate={async (templateId) => {
                  const result = await adminApi.applyTemplate(session.backendToken!, id, templateId);
                  setDimensions(result.dimensions);
                }}
                onSaveDimensions={async (dims) => {
                  const result = await adminApi.updateDimensions(session.backendToken!, id, dims);
                  setDimensions(result);
                }}
              />
            </section>

            <hr className="border-gray-800" />

            <section>
              <ExpertPicker
                experts={experts}
                assignments={assignments}
                onAssign={async (expertId) => {
                  await adminApi.assignExpert(session.backendToken!, id, expertId);
                  loadAll();
                }}
                onRemoveAssignment={async (assignmentId) => {
                  await adminApi.deleteAssignment(session.backendToken!, assignmentId);
                  loadAll();
                }}
              />
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
