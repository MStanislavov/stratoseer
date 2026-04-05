import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { Play, Ban, Trash2 } from "lucide-react"
import { listRuns, createRun, cancelRun, deleteRun, bulkDeleteRuns } from "@/api/runs"
import type { Run, RunCreate } from "@/api/types"
import { PageHeader } from "@/components/shared/PageHeader"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"
import { EmptyState } from "@/components/shared/EmptyState"
import { StatusBadge } from "@/components/shared/StatusBadge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
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
import { toast } from "sonner"

export default function RunsListPage() {
  const { profileId } = useParams()
  const navigate = useNavigate()
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<RunCreate["mode"]>("weekly")
  const [cancelTarget, setCancelTarget] = useState<Run | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Run | null>(null)
  const [filterMode, setFilterMode] = useState<string>("all")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)

  function load() {
    if (!profileId) return
    listRuns(profileId)
      .then(setRuns)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [profileId])

  async function handleStart() {
    if (!profileId) return
    const run = await createRun(profileId, { mode })
    toast.success(`Run started (${mode})`)
    navigate(`/profiles/${profileId}/runs/${run.id}`)
  }

  async function handleCancel(run: Run) {
    if (!profileId) return
    await cancelRun(profileId, run.id)
    toast.success("Cancellation requested")
    setCancelTarget(null)
    load()
  }

  async function handleDelete(run: Run) {
    if (!profileId) return
    await deleteRun(profileId, run.id)
    toast.success("Run and all results deleted")
    setDeleteTarget(null)
    load()
  }

  // Filtered runs visible in the table (excludes cover_letter)
  const visibleRuns = runs.filter(
    (r) => r.mode !== "cover_letter" && (filterMode === "all" || r.mode === filterMode),
  )

  // Only non-executing runs can be selected for bulk delete
  const deletableIds = new Set(
    visibleRuns.filter((r) => r.status !== "running" && r.status !== "pending").map((r) => r.id),
  )

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (selected.size === deletableIds.size) {
      setSelected(new Set())
    } else {
      setSelected(new Set(deletableIds))
    }
  }

  async function handleBulkDelete() {
    if (!profileId || selected.size === 0) return
    const result = await bulkDeleteRuns(profileId, [...selected])
    const count = result.deleted.length
    const skippedCount = result.skipped.length
    if (count > 0) toast.success(`Deleted ${count} run${count > 1 ? "s" : ""}`)
    if (skippedCount > 0) toast.warning(`Skipped ${skippedCount} run${skippedCount > 1 ? "s" : ""} (still executing or not found)`)
    setSelected(new Set())
    setBulkDeleteOpen(false)
    load()
  }

  if (loading) return <LoadingSpinner />

  return (
    <div>
      <PageHeader title="Runs" description="Pipeline execution history" />

      {/* Start run controls */}
      <Card className="p-4 mb-6">
        <div className="flex items-center gap-3">
          <Select value={mode} onValueChange={(v) => setMode(v as RunCreate["mode"])}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="daily">Daily</SelectItem>
              <SelectItem value="weekly">Weekly</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={handleStart}>
            <Play className="h-4 w-4 mr-2" /> Start Run
          </Button>
        </div>
      </Card>

      {visibleRuns.length === 0 ? (
        <EmptyState
          icon={<Play className="h-10 w-10" />}
          title="No runs yet"
          description="Start your first pipeline run above."
        />
      ) : (
        <>
        <div className="mb-4 flex items-center gap-3">
          <div className="max-w-xs">
            <Select value={filterMode} onValueChange={(v) => { setFilterMode(v); setSelected(new Set()) }}>
              <SelectTrigger>
                <SelectValue placeholder="Filter by mode..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All modes</SelectItem>
                <SelectItem value="daily">Daily</SelectItem>
                <SelectItem value="weekly">Weekly</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {selected.size > 0 && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setBulkDeleteOpen(true)}
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete {selected.size} run{selected.size > 1 ? "s" : ""}
            </Button>
          )}
        </div>
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={deletableIds.size > 0 && selected.size === deletableIds.size}
                    onCheckedChange={toggleSelectAll}
                    aria-label="Select all"
                  />
                </TableHead>
                <TableHead>Run ID</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Verifier</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Finished</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleRuns.map((r) => (
                <TableRow
                  key={r.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/profiles/${profileId}/runs/${r.id}`)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {deletableIds.has(r.id) && (
                      <Checkbox
                        checked={selected.has(r.id)}
                        onCheckedChange={() => toggleSelect(r.id)}
                        aria-label={`Select run ${r.id.slice(0, 8)}`}
                      />
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.id.slice(0, 8)}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{r.mode}</Badge>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.status} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.verifier_status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {r.started_at ? new Date(r.started_at).toLocaleString() : "-"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {r.finished_at ? new Date(r.finished_at).toLocaleString() : "-"}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {(r.status === "running" || r.status === "pending") && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation()
                            setCancelTarget(r)
                          }}
                        >
                          <Ban className="h-4 w-4" />
                        </Button>
                      )}
                      {r.status !== "running" && r.status !== "pending" && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleteTarget(r)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
        </>
      )}

      <AlertDialog open={!!cancelTarget} onOpenChange={() => setCancelTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel run?</AlertDialogTitle>
            <AlertDialogDescription>
              This will request cancellation of run {cancelTarget?.id.slice(0, 8)}.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>No</AlertDialogCancel>
            <AlertDialogAction onClick={() => cancelTarget && handleCancel(cancelTarget)}>
              Yes, cancel
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete run and all results?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete run {deleteTarget?.id.slice(0, 8)} and all
              jobs, certifications, courses, events, groups, trends, and cover letters
              produced by it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleteTarget && handleDelete(deleteTarget)}>
              Delete all
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={bulkDeleteOpen} onOpenChange={setBulkDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selected.size} run{selected.size > 1 ? "s" : ""} and all results?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the selected runs and all their
              jobs, certifications, courses, events, groups, trends, and cover letters.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleBulkDelete}>
              Delete all
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
