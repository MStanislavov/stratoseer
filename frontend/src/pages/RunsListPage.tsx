import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { Play, Ban, Trash2 } from "lucide-react"
import { listRuns, createRun, cancelRun, deleteRun } from "@/api/runs"
import type { Run, RunCreate } from "@/api/types"
import { PageHeader } from "@/components/shared/PageHeader"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"
import { EmptyState } from "@/components/shared/EmptyState"
import { StatusBadge } from "@/components/shared/StatusBadge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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

      {runs.filter((r) => r.mode !== "cover_letter").length === 0 ? (
        <EmptyState
          icon={<Play className="h-10 w-10" />}
          title="No runs yet"
          description="Start your first pipeline run above."
        />
      ) : (
        <>
        <div className="mb-4 max-w-xs">
          <Select value={filterMode} onValueChange={setFilterMode}>
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
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
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
              {runs.filter((r) => r.mode !== "cover_letter" && (filterMode === "all" || r.mode === filterMode)).map((r) => (
                <TableRow
                  key={r.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/profiles/${profileId}/runs/${r.id}`)}
                >
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
    </div>
  )
}
