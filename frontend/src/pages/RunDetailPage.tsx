import { useEffect, useState, useCallback } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { RefreshCw, Ban, GitCompare, Eye, Check, AlertTriangle, X, ChevronRight, Copy } from "lucide-react"
import { getRun, cancelRun } from "@/api/runs"
import { getAudit, replay } from "@/api/audit"
import { listJobs, listCertifications, listCourses, listEvents, listGroups, listTrends } from "@/api/results"
import type { Run, AuditEvent, SSEEvent } from "@/api/types"
import { useSSE } from "@/hooks/useSSE"
import { PageHeader } from "@/components/shared/PageHeader"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"
import { StatusBadge } from "@/components/shared/StatusBadge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { toast } from "sonner"

const AGENTS_BY_MODE: Record<string, string[]> = {
  daily: ["goal_extractor", "web_scrapers", "url_validator", "data_formatter", "audit_writer"],
  weekly: ["goal_extractor", "web_scrapers", "url_validator", "data_formatter", "ceo", "cfo", "audit_writer"],
  cover_letter: ["cover_letter_agent", "audit_writer"],
}

type AgentStatus = "idle" | "running" | "complete" | "partial" | "failed"

function deriveAgentStatuses(mode: string, events: SSEEvent[]): Record<string, AgentStatus> {
  const agents = AGENTS_BY_MODE[mode] ?? AGENTS_BY_MODE.daily
  const statuses: Record<string, AgentStatus> = {}
  for (const name of agents) statuses[name] = "idle"
  for (const e of events) {
    if (e.agent && e.type === "agent_started") statuses[e.agent] = "running"
    if (e.agent && e.type === "agent_completed") {
      if (e.verification_status === "fail") {
        statuses[e.agent] = "failed"
      } else if (e.verification_status === "partial") {
        statuses[e.agent] = "partial"
      } else {
        statuses[e.agent] = "complete"
      }
    }
  }
  return statuses
}

function deriveAgentStatusesFromAudit(mode: string, events: AuditEvent[]): Record<string, AgentStatus> {
  const agents = AGENTS_BY_MODE[mode] ?? AGENTS_BY_MODE.daily
  const statuses: Record<string, AgentStatus> = {}
  for (const name of agents) statuses[name] = "idle"
  for (const e of events) {
    if (e.event_type === "agent_start" && agents.includes(e.agent)) {
      statuses[e.agent] = "running"
    }
    if (e.event_type === "agent_end" && agents.includes(e.agent)) {
      statuses[e.agent] = "complete"
    }
    if (e.event_type === "verifier_result" && agents.includes(e.agent)) {
      const status = (e.data as Record<string, unknown>)?.status
      if (status === "fail") statuses[e.agent] = "failed"
      else if (status === "partial") statuses[e.agent] = "partial"
    }
  }
  return statuses
}

export default function RunDetailPage() {
  const { profileId, runId } = useParams()
  const navigate = useNavigate()
  const [run, setRun] = useState<Run | null>(null)
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([])
  const [outputs, setOutputs] = useState<Record<string, unknown[]> | null>(null)
  const [loading, setLoading] = useState(true)
  const { events: sseEvents, done: sseDone } = useSSE(profileId, runId)

  const load = useCallback(() => {
    if (!profileId || !runId) return
    getRun(profileId, runId)
      .then((r) => {
        setRun(r)
        if (r.status === "completed" || r.status === "failed") {
          Promise.all([
            listJobs(profileId, runId),
            listCertifications(profileId, runId),
            listCourses(profileId, runId),
            listEvents(profileId, runId),
            listGroups(profileId, runId),
            listTrends(profileId, runId),
          ]).then(([j, ce, co, ev, gr, tr]) => {
            setOutputs({ jobs: j, certifications: ce, courses: co, events: ev, groups: gr, trends: tr })
          })
        }
      })
      .finally(() => setLoading(false))
    getAudit(profileId, runId)
      .then((a) => setAuditEvents(a.events))
      .catch(() => {})
  }, [profileId, runId])

  useEffect(() => { load() }, [load])

  // Re-fetch audit trail whenever new SSE events arrive
  useEffect(() => {
    if (!profileId || !runId || sseEvents.length === 0) return
    getAudit(profileId, runId)
      .then((a) => setAuditEvents(a.events))
      .catch(() => {})
  }, [profileId, runId, sseEvents.length])

  // Refresh run data when SSE indicates completion
  useEffect(() => {
    if (sseDone) load()
  }, [sseDone, load])

  async function handleCancel() {
    if (!profileId || !runId) return
    await cancelRun(profileId, runId)
    toast.success("Cancellation requested")
    load()
  }

  async function handleReplay(mode: "strict" | "refresh") {
    if (!profileId || !runId) return
    const res = await replay(profileId, runId, { mode })
    toast.success(`Replay complete (${mode}): ${res.run_id.slice(0, 8)}`)
  }

  if (loading) return <LoadingSpinner />
  if (!run) return <p className="text-muted-foreground">Run not found.</p>

  const isActive = run.status === "running" || run.status === "pending"
  const agentStatuses = sseEvents.length > 0
    ? deriveAgentStatuses(run.mode, sseEvents)
    : auditEvents.length > 0
      ? deriveAgentStatusesFromAudit(run.mode, auditEvents)
      : deriveAgentStatuses(run.mode, [])

  return (
    <div>
      <PageHeader
        title={`Run ${run.id.slice(0, 8)}`}
        actions={
          <div className="flex gap-2">
            {isActive && (
              <Button variant="destructive" onClick={handleCancel}>
                <Ban className="h-4 w-4 mr-2" /> Cancel
              </Button>
            )}
            {!isActive && (
              <>
                <Button variant="outline" onClick={() => handleReplay("strict")}>
                  <RefreshCw className="h-4 w-4 mr-2" /> Replay (strict)
                </Button>
                <Button variant="outline" onClick={() => handleReplay("refresh")}>
                  <GitCompare className="h-4 w-4 mr-2" /> Replay (refresh)
                </Button>
              </>
            )}
          </div>
        }
      />

      {/* Run info card */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Mode</p>
              <Badge variant="outline">{run.mode}</Badge>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Status</p>
              <StatusBadge status={run.status} />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Duration</p>
              <p className="text-sm font-medium">
                {run.started_at && run.finished_at
                  ? `${((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000).toFixed(1)}s`
                  : run.started_at
                    ? "In progress..."
                    : "-"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Pipeline progress stepper */}
      <Card className="mb-6 border-l-4 border-l-indigo-500">
        <CardHeader>
          <CardTitle className="text-base">Pipeline Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <PipelineStepper agents={AGENTS_BY_MODE[run.mode] ?? AGENTS_BY_MODE.daily} statuses={agentStatuses} />
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="audit">
        <TabsList>
          <TabsTrigger value="audit">Audit Trail</TabsTrigger>
          <TabsTrigger value="outputs">Outputs</TabsTrigger>
          {!isActive && run.status === "completed" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(`/profiles/${profileId}/results?run_id=${runId}`)}
              className="text-primary"
            >
              <Eye className="h-4 w-4 mr-1" /> View Results
            </Button>
          )}
        </TabsList>

        <TabsContent value="audit">
          <AuditTimeline events={auditEvents} />
        </TabsContent>

        <TabsContent value="outputs">
          <Card>
            <CardContent className="pt-6">
              {outputs ? (
                <pre className="bg-muted rounded-md p-4 text-xs font-mono overflow-x-auto whitespace-pre-wrap max-h-[600px]">
                  {JSON.stringify(outputs, null, 2)}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {run.status === "completed" || run.status === "failed"
                    ? "Loading outputs..."
                    : "Outputs will be available after the run completes."}
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

function PipelineStepper({ agents, statuses }: { agents: string[]; statuses: Record<string, AgentStatus> }) {
  const stepCircle = (s: AgentStatus) => {
    switch (s) {
      case "complete":
        return (
          <div className="h-8 w-8 rounded-full bg-indigo-600 flex items-center justify-center">
            <Check className="h-4 w-4 text-white" />
          </div>
        )
      case "running":
        return (
          <div className="h-8 w-8 rounded-full bg-indigo-500 ring-2 ring-indigo-300 animate-pulse flex items-center justify-center">
            <div className="h-2 w-2 rounded-full bg-white" />
          </div>
        )
      case "partial":
        return (
          <div className="h-8 w-8 rounded-full bg-amber-500 flex items-center justify-center">
            <AlertTriangle className="h-4 w-4 text-white" />
          </div>
        )
      case "failed":
        return (
          <div className="h-8 w-8 rounded-full bg-rose-500 flex items-center justify-center">
            <X className="h-4 w-4 text-white" />
          </div>
        )
      default:
        return <div className="h-8 w-8 rounded-full border-2 border-gray-300 bg-background" />
    }
  }

  const lineColor = (prevStatus: AgentStatus) =>
    prevStatus === "complete" ? "bg-indigo-600" : "bg-gray-200"

  return (
    <div className="flex items-start overflow-x-auto">
      {agents.map((name, i) => (
        <div key={name} className="flex items-start" style={{ minWidth: 0 }}>
          <div className="flex flex-col items-center" style={{ minWidth: "5rem" }}>
            {stepCircle(statuses[name])}
            <span className="mt-2 text-xs text-muted-foreground text-center leading-tight">
              {name.replace(/_/g, " ")}
            </span>
          </div>
          {i < agents.length - 1 && (
            <div className="flex items-center" style={{ paddingTop: "0.875rem" }}>
              <div className={`h-0.5 w-8 ${lineColor(statuses[name])}`} />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function AuditTimeline({ events }: { events: AuditEvent[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground py-4">No audit events recorded.</p>
  }

  const dotColor: Record<string, string> = {
    agent_start: "bg-blue-500",
    agent_end: "bg-green-500",
    verifier_result: "bg-yellow-500",
    error: "bg-red-500",
  }

  const toggle = (i: number) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(i) ? next.delete(i) : next.add(i)
      return next
    })

  return (
    <div className="relative ml-4 border-l pl-6 space-y-4 py-4">
      {events.map((e, i) => {
        const hasData = e.data && Object.keys(e.data).length > 0
        const isOpen = expanded.has(i)
        return (
          <div key={i} className="relative">
            <span
              className={`absolute -left-[1.85rem] top-1.5 h-3 w-3 rounded-full border-2 border-background ${dotColor[e.event_type] ?? "bg-gray-400"}`}
            />
            <p className="text-xs text-muted-foreground">{e.timestamp}</p>
            {hasData ? (
              <button
                type="button"
                onClick={() => toggle(i)}
                className="flex items-center gap-1 text-sm font-medium hover:underline cursor-pointer"
              >
                <ChevronRight className={`h-3.5 w-3.5 transition-transform ${isOpen ? "rotate-90" : ""}`} />
                {e.agent}, <span className="font-normal text-muted-foreground">{e.event_type}</span>
              </button>
            ) : (
              <p className="text-sm font-medium">
                {e.agent}, <span className="font-normal text-muted-foreground">{e.event_type}</span>
              </p>
            )}
            {hasData && isOpen && (
              <div className="relative mt-1">
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(JSON.stringify(e.data, null, 2))
                    toast.success("Copied to clipboard")
                  }}
                  className="absolute top-2 right-2 p-1 rounded hover:bg-background/80 text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
                <pre className="bg-muted rounded p-2 pr-8 text-xs font-mono overflow-x-auto max-h-80 overflow-y-auto">
                  {JSON.stringify(e.data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
