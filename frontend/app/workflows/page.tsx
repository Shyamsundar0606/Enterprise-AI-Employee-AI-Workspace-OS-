"use client";

import { useEffect, useState } from "react";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Workflow = { id: string; name: string; status: string; current_step: number };
type Approval = {
  id: string;
  workflow_id: string;
  workflow_step_id: string;
  status: string;
  connector_id: string;
  operation: string;
  sanitized_arguments: Record<string, unknown>;
  risk_level: string;
};

function headers(): HeadersInit {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState("");

  const load = async () => {
    const [workflowResponse, approvalResponse] = await Promise.all([
      fetch(`${apiBase}/api/v1/workflows`, { headers: headers() }),
      fetch(`${apiBase}/api/v1/approvals`, { headers: headers() }),
    ]);
    if (!workflowResponse.ok || !approvalResponse.ok) {
      setError("Sign in before viewing workflows and approvals.");
      return;
    }
    setWorkflows(await workflowResponse.json());
    setApprovals(await approvalResponse.json());
  };

  useEffect(() => {
    void load();
  }, []);

  const decide = async (approvalId: string, decision: "approve" | "reject") => {
    const response = await fetch(`${apiBase}/api/v1/approvals/${approvalId}/${decision}`, {
      method: "POST",
      headers: headers(),
    });
    if (!response.ok) setError("Approval decision could not be applied.");
    await load();
  };

  return (
    <main className="min-h-screen bg-zinc-950 p-6 text-zinc-100">
      <div className="mx-auto max-w-4xl space-y-6">
        <header><p className="text-xs uppercase tracking-widest text-zinc-500">Enterprise AI Employee</p><h1 className="text-2xl font-semibold">Workflows & approvals</h1></header>
        {error && <p className="rounded border border-red-800 bg-red-950 p-3 text-sm text-red-200">{error}</p>}
        <section className="rounded-xl border border-zinc-800 p-4"><h2 className="mb-3 font-medium">Workflows</h2>{workflows.map((workflow) => <div key={workflow.id} className="flex justify-between border-t border-zinc-800 py-3 text-sm"><span>{workflow.name}</span><span className="text-zinc-400">{workflow.status} · step {workflow.current_step}</span></div>)}</section>
        <section className="rounded-xl border border-zinc-800 p-4"><h2 className="mb-3 font-medium">Pending approvals</h2>{approvals.map((approval) => <article key={approval.id} className="border-t border-zinc-800 py-3"><p className="font-medium">{approval.connector_id}.{approval.operation}</p><p className="text-sm text-zinc-400">Risk: {approval.risk_level}</p><pre className="my-2 overflow-auto text-xs text-zinc-400">{JSON.stringify(approval.sanitized_arguments, null, 2)}</pre><button className="mr-2 rounded bg-emerald-500 px-3 py-1 text-sm text-black" onClick={() => void decide(approval.id, "approve")}>Approve</button><button className="rounded bg-red-500 px-3 py-1 text-sm text-black" onClick={() => void decide(approval.id, "reject")}>Reject</button></article>)}</section>
      </div>
    </main>
  );
}
