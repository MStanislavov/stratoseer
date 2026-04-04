import { useEffect, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import {
  Briefcase, GraduationCap, BookOpen, Calendar, Users, TrendingUp,
  Search, Pencil, Trash2, Check, X, Target, ShieldAlert,
} from "lucide-react"
import {
  listJobs, listCertifications, listCourses, listEvents, listGroups, listTrends,
  updateResult, deleteResult, getInsights,
} from "@/api/results"
import { listRuns } from "@/api/runs"
import type { JobOpportunity, Certification, Course, Event, Group, Trend, Run, ExecutiveInsights } from "@/api/types"
import { PageHeader } from "@/components/shared/PageHeader"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"
import { EmptyState } from "@/components/shared/EmptyState"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

function dedup<T extends { created_at: string }>(
  items: T[],
  keyFn: (item: T) => string,
): T[] {
  const map = new Map<string, T>()
  for (const item of items) {
    const key = keyFn(item)
    const existing = map.get(key)
    if (!existing || item.created_at > existing.created_at) {
      map.set(key, item)
    }
  }
  return [...map.values()]
}

export default function OpportunitiesPage() {
  const { profileId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const runId = searchParams.get("run_id") ?? undefined
  const [jobs, setJobs] = useState<JobOpportunity[]>([])
  const [certifications, setCertifications] = useState<Certification[]>([])
  const [courses, setCourses] = useState<Course[]>([])
  const [events, setEvents] = useState<Event[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [trends, setTrends] = useState<Trend[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [insights, setInsights] = useState<ExecutiveInsights | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState("")

  const selectedRun = runs.find((r) => r.id === runId)
  const isWeekly = selectedRun?.mode === "weekly"

  useEffect(() => {
    if (!profileId) return
    setLoading(true)
    setInsights(null)
    Promise.all([
      listJobs(profileId, runId),
      listCertifications(profileId, runId),
      listCourses(profileId, runId),
      listEvents(profileId, runId),
      listGroups(profileId, runId),
      listTrends(profileId, runId),
      listRuns(profileId),
    ])
      .then(([j, ce, co, ev, gr, tr, r]) => {
        setJobs(runId ? j : dedup(j, (x) => `${x.title}|${x.company ?? ""}`))
        setCertifications(runId ? ce : dedup(ce, (x) => `${x.title}|${x.provider ?? ""}`))
        setCourses(runId ? co : dedup(co, (x) => `${x.title}|${x.platform ?? ""}`))
        setEvents(runId ? ev : dedup(ev, (x) => `${x.title}|${x.organizer ?? ""}`))
        setGroups(runId ? gr : dedup(gr, (x) => `${x.title}|${x.platform ?? ""}`))
        setTrends(runId ? tr : dedup(tr, (x) => `${x.title}|${x.source ?? ""}`))
        // Only show runs that have at least one result
        const allResults = [...j, ...ce, ...co, ...ev, ...gr, ...tr]
        const runIdsWithResults = new Set(allResults.map((x) => x.run_id))
        const filteredRuns = r.filter((run) => runIdsWithResults.has(run.id))
        setRuns(filteredRuns)
        // Fetch insights for weekly runs
        const matchedRun = runId ? filteredRuns.find((run) => run.id === runId) : undefined
        if (matchedRun?.mode === "weekly") {
          getInsights(profileId, runId!).then(setInsights).catch(() => setInsights(null))
        }
      })
      .finally(() => setLoading(false))
  }, [profileId, runId])

  function handleRunFilterChange(value: string) {
    if (value === "all") {
      searchParams.delete("run_id")
    } else {
      searchParams.set("run_id", value)
    }
    setSearchParams(searchParams)
  }

  if (loading) return <LoadingSpinner />

  const q = filter.toLowerCase()
  const totalCount = jobs.length + certifications.length + courses.length + events.length + groups.length + trends.length

  return (
    <div>
      <PageHeader title="Results" description="Discovered career opportunities and resources" />

      <div className="mb-4 max-w-xs">
        <Select value={runId ?? "all"} onValueChange={handleRunFilterChange}>
          <SelectTrigger>
            <SelectValue placeholder="Filter by run..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All runs</SelectItem>
            {runs.map((r) => (
              <SelectItem key={r.id} value={r.id}>
                {r.mode} - {r.started_at ? new Date(r.started_at).toLocaleDateString() : "pending"} ({r.id.slice(0, 8)})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {totalCount > 0 && (
        <div className="relative mb-6 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by title..."
            className="pl-9"
          />
        </div>
      )}

      {isWeekly && insights && (
        <div className="grid gap-4 md:grid-cols-2 mb-6">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Target className="h-5 w-5 text-primary" />
                <CardTitle className="text-lg">Strategic Recommendations</CardTitle>
              </div>
              {insights.ceo_summary && (
                <p className="text-sm text-muted-foreground mt-1">{insights.ceo_summary}</p>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {insights.strategic_recommendations.length === 0 ? (
                <p className="text-sm text-muted-foreground">No recommendations available.</p>
              ) : (
                insights.strategic_recommendations.map((rec, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-md border p-3">
                    <Badge
                      variant={rec.priority === "high" ? "destructive" : rec.priority === "medium" ? "default" : "secondary"}
                      className="mt-0.5 shrink-0 text-xs"
                    >
                      {rec.priority}
                    </Badge>
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{rec.area}</p>
                      <p className="text-sm text-muted-foreground mt-0.5">{rec.recommendation}</p>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-orange-500" />
                <CardTitle className="text-lg">Risk Assessment</CardTitle>
              </div>
              {insights.cfo_summary && (
                <p className="text-sm text-muted-foreground mt-1">{insights.cfo_summary}</p>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {insights.risk_assessments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No risk assessments available.</p>
              ) : (
                insights.risk_assessments.map((ra, i) => (
                  <div key={i} className="rounded-md border p-3 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">{ra.area}</p>
                      <Badge
                        variant={ra.risk_level === "high" ? "destructive" : ra.risk_level === "medium" ? "default" : "secondary"}
                        className="text-xs"
                      >
                        {ra.risk_level} risk
                      </Badge>
                    </div>
                    <div className="flex gap-4 text-xs text-muted-foreground">
                      <span>Time: {ra.time_investment}</span>
                      <span>ROI: {ra.roi_estimate}</span>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {totalCount === 0 ? (
        !(isWeekly && insights) && (
          <EmptyState
            icon={<Briefcase className="h-10 w-10" />}
            title="No results yet"
            description="Run a daily or weekly pipeline to discover opportunities."
          />
        )
      ) : (
        <Tabs defaultValue="jobs">
          <TabsList>
            <TabsTrigger value="jobs">Jobs ({jobs.length})</TabsTrigger>
            <TabsTrigger value="certifications">Certifications ({certifications.length})</TabsTrigger>
            <TabsTrigger value="courses">Courses ({courses.length})</TabsTrigger>
            <TabsTrigger value="events">Events ({events.length})</TabsTrigger>
            <TabsTrigger value="groups">Groups ({groups.length})</TabsTrigger>
            <TabsTrigger value="trends">Trends ({trends.length})</TabsTrigger>
          </TabsList>

          <TabsContent value="jobs">
            <ResultGrid
              items={jobs.filter((j) => !q || j.title.toLowerCase().includes(q) || (j.company ?? "").toLowerCase().includes(q))}
              emptyLabel="No jobs found"
              renderItem={(j) => (
                <ResultCard
                  key={j.id}
                  id={j.id}
                  icon={<Briefcase className="h-4 w-4" />}
                  title={j.title}
                  subtitle={j.company}
                  description={j.description}
                  url={j.url}
                  badges={[j.location, j.salary_range].filter(Boolean) as string[]}
                  onEdit={async (id, newTitle) => {
                    await updateResult(profileId!, "jobs", id, { title: newTitle })
                    setJobs((prev) => prev.map((x) => (x.id === id ? { ...x, title: newTitle } : x)))
                  }}
                  onDelete={async (id) => {
                    await deleteResult(profileId!, "jobs", id)
                    setJobs((prev) => prev.filter((x) => x.id !== id))
                  }}
                  onForceDelete={async (id) => {
                    await deleteResult(profileId!, "jobs", id, true)
                    setJobs((prev) => prev.filter((x) => x.id !== id))
                  }}
                />
              )}
            />
          </TabsContent>

          <TabsContent value="certifications">
            <ResultGrid
              items={certifications.filter((c) => !q || c.title.toLowerCase().includes(q) || (c.provider ?? "").toLowerCase().includes(q))}
              emptyLabel="No certifications found"
              renderItem={(c) => (
                <ResultCard
                  key={c.id}
                  id={c.id}
                  icon={<GraduationCap className="h-4 w-4" />}
                  title={c.title}
                  subtitle={c.provider}
                  description={c.description}
                  url={c.url}
                  badges={[c.cost, c.duration].filter(Boolean) as string[]}
                  onEdit={async (id, newTitle) => {
                    await updateResult(profileId!, "certifications", id, { title: newTitle })
                    setCertifications((prev) => prev.map((x) => (x.id === id ? { ...x, title: newTitle } : x)))
                  }}
                  onDelete={async (id) => {
                    await deleteResult(profileId!, "certifications", id)
                    setCertifications((prev) => prev.filter((x) => x.id !== id))
                  }}
                />
              )}
            />
          </TabsContent>

          <TabsContent value="courses">
            <ResultGrid
              items={courses.filter((c) => !q || c.title.toLowerCase().includes(q) || (c.platform ?? "").toLowerCase().includes(q))}
              emptyLabel="No courses found"
              renderItem={(c) => (
                <ResultCard
                  key={c.id}
                  id={c.id}
                  icon={<BookOpen className="h-4 w-4" />}
                  title={c.title}
                  subtitle={c.platform}
                  description={c.description}
                  url={c.url}
                  badges={[c.cost, c.duration].filter(Boolean) as string[]}
                  onEdit={async (id, newTitle) => {
                    await updateResult(profileId!, "courses", id, { title: newTitle })
                    setCourses((prev) => prev.map((x) => (x.id === id ? { ...x, title: newTitle } : x)))
                  }}
                  onDelete={async (id) => {
                    await deleteResult(profileId!, "courses", id)
                    setCourses((prev) => prev.filter((x) => x.id !== id))
                  }}
                />
              )}
            />
          </TabsContent>

          <TabsContent value="events">
            <ResultGrid
              items={events.filter((e) => !q || e.title.toLowerCase().includes(q) || (e.organizer ?? "").toLowerCase().includes(q))}
              emptyLabel="No events found"
              renderItem={(e) => (
                <ResultCard
                  key={e.id}
                  id={e.id}
                  icon={<Calendar className="h-4 w-4" />}
                  title={e.title}
                  subtitle={e.organizer}
                  description={e.description}
                  url={e.url}
                  badges={[e.event_date, e.location].filter(Boolean) as string[]}
                  onEdit={async (id, newTitle) => {
                    await updateResult(profileId!, "events", id, { title: newTitle })
                    setEvents((prev) => prev.map((x) => (x.id === id ? { ...x, title: newTitle } : x)))
                  }}
                  onDelete={async (id) => {
                    await deleteResult(profileId!, "events", id)
                    setEvents((prev) => prev.filter((x) => x.id !== id))
                  }}
                />
              )}
            />
          </TabsContent>

          <TabsContent value="groups">
            <ResultGrid
              items={groups.filter((g) => !q || g.title.toLowerCase().includes(q) || (g.platform ?? "").toLowerCase().includes(q))}
              emptyLabel="No groups found"
              renderItem={(g) => (
                <ResultCard
                  key={g.id}
                  id={g.id}
                  icon={<Users className="h-4 w-4" />}
                  title={g.title}
                  subtitle={g.platform}
                  description={g.description}
                  url={g.url}
                  badges={g.member_count ? [`${g.member_count.toLocaleString()} members`] : []}
                  onEdit={async (id, newTitle) => {
                    await updateResult(profileId!, "groups", id, { title: newTitle })
                    setGroups((prev) => prev.map((x) => (x.id === id ? { ...x, title: newTitle } : x)))
                  }}
                  onDelete={async (id) => {
                    await deleteResult(profileId!, "groups", id)
                    setGroups((prev) => prev.filter((x) => x.id !== id))
                  }}
                />
              )}
            />
          </TabsContent>

          <TabsContent value="trends">
            <ResultGrid
              items={trends.filter((t) => !q || t.title.toLowerCase().includes(q) || (t.category ?? "").toLowerCase().includes(q))}
              emptyLabel="No trends found"
              renderItem={(t) => (
                <ResultCard
                  key={t.id}
                  id={t.id}
                  icon={<TrendingUp className="h-4 w-4" />}
                  title={t.title}
                  subtitle={t.source}
                  description={t.description}
                  url={t.url}
                  badges={[t.category].filter(Boolean) as string[]}
                  relevance={t.relevance}
                  onEdit={async (id, newTitle) => {
                    await updateResult(profileId!, "trends", id, { title: newTitle })
                    setTrends((prev) => prev.map((x) => (x.id === id ? { ...x, title: newTitle } : x)))
                  }}
                  onDelete={async (id) => {
                    await deleteResult(profileId!, "trends", id)
                    setTrends((prev) => prev.filter((x) => x.id !== id))
                  }}
                />
              )}
            />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}

function ResultGrid<T>({
  items,
  emptyLabel,
  renderItem,
}: {
  items: T[]
  emptyLabel: string
  renderItem: (item: T) => React.ReactNode
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-4">{emptyLabel}</p>
  }
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mt-4">
      {items.map(renderItem)}
    </div>
  )
}

function ResultCard({
  id,
  icon,
  title,
  subtitle,
  description,
  url,
  badges,
  onEdit,
  relevance,
  onDelete,
  onForceDelete,
}: {
  id: string
  icon: React.ReactNode
  title: string
  subtitle: string | null | undefined
  description: string | null | undefined
  url: string | null | undefined
  badges: string[]
  relevance?: string | null
  onEdit?: (id: string, newTitle: string) => Promise<void>
  onDelete?: (id: string) => Promise<void>
  onForceDelete?: (id: string) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(title)
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [conflictMessage, setConflictMessage] = useState("")

  async function handleSave() {
    if (!onEdit || editTitle.trim() === "" || editTitle === title) {
      setEditing(false)
      setEditTitle(title)
      return
    }
    setSaving(true)
    try {
      await onEdit(id, editTitle.trim())
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!onDelete) return
    try {
      await onDelete(id)
      setConfirmDelete(false)
    } catch (err: unknown) {
      if (err && typeof err === "object" && "status" in err && (err as { status: number }).status === 409) {
        setConfirmDelete(false)
        setConflictMessage((err as { detail?: string }).detail ?? "This job has linked cover letters. Delete them too?")
      }
    }
  }

  async function handleForceConfirm() {
    setConflictMessage("")
    if (onForceDelete) {
      await onForceDelete(id)
    }
  }

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-start gap-2 min-w-0 flex-1">
              <span className="text-muted-foreground mt-0.5 shrink-0">{icon}</span>
              {editing ? (
                <div className="flex items-center gap-1 flex-1">
                  <Input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="h-7 text-sm"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSave()
                      if (e.key === "Escape") {
                        setEditing(false)
                        setEditTitle(title)
                      }
                    }}
                  />
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="text-muted-foreground hover:text-foreground p-0.5"
                  >
                    <Check className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => {
                      setEditing(false)
                      setEditTitle(title)
                    }}
                    className="text-muted-foreground hover:text-foreground p-0.5"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <CardTitle className="text-base leading-snug">{title}</CardTitle>
              )}
            </div>
            {!editing && (onEdit || onDelete) && (
              <div className="flex gap-1 shrink-0">
                {onEdit && (
                  <button
                    onClick={() => {
                      setEditTitle(title)
                      setEditing(true)
                    }}
                    className="text-muted-foreground hover:text-foreground p-0.5"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
                {onDelete && (
                  <button
                    onClick={() => setConfirmDelete(true)}
                    className="text-muted-foreground hover:text-destructive p-0.5"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {subtitle && <p className="text-xs text-muted-foreground mb-2">{subtitle}</p>}
          {description && <p className="text-sm line-clamp-2">{description}</p>}
          {badges.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {badges.map((b) => (
                <Badge key={b} variant="secondary" className="text-xs">
                  {b}
                </Badge>
              ))}
            </div>
          )}
          {relevance && (
            <p className="text-xs text-muted-foreground mt-1 break-words">{relevance}</p>
          )}
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary hover:underline mt-2 inline-block"
            >
              View source
            </a>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this item?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. "{title}" will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!conflictMessage} onOpenChange={() => setConflictMessage("")}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete job and cover letters?</AlertDialogTitle>
            <AlertDialogDescription>{conflictMessage}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleForceConfirm}>
              Delete all
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
