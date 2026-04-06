import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Users, Play, Plus, LayoutDashboard, Upload } from "lucide-react"
import { createProfile, importProfile, updateProfile } from "@/api/profiles"
import { ApiError } from "@/api/client"
import { listAllRuns } from "@/api/runs"
import type { Run } from "@/api/types"
import { useProfiles } from "@/contexts/ProfileContext"
import { PageHeader } from "@/components/shared/PageHeader"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"
import { EmptyState } from "@/components/shared/EmptyState"
import { StatusBadge } from "@/components/shared/StatusBadge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"

export default function DashboardPage() {
  const { profiles, loading: profilesLoading, refresh: refreshProfiles } = useProfiles()
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [importConflict, setImportConflict] = useState<{ existingId: string; data: Record<string, unknown> } | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    listAllRuns(10)
      .then(setRuns)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function handleCreate() {
    if (!newName.trim()) return
    try {
      const profile = await createProfile({ name: newName.trim() })
      setDialogOpen(false)
      setNewName("")
      await refreshProfiles()
      navigate(`/profiles/${profile.id}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) return
      throw err
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const existing = profiles.find((p) => p.name === data.name)
      if (existing) {
        setImportConflict({ existingId: existing.id, data })
        e.target.value = ""
        return
      }
      const created = await importProfile(data)
      await refreshProfiles()
      toast.success(`Profile "${created.name}" imported`)
      navigate(`/profiles/${created.id}`)
    } catch {
      toast.error("Failed to import profile. Check the file format.")
    }
    e.target.value = ""
  }

  async function handleImportReplace() {
    if (!importConflict) return
    const { existingId, data } = importConflict
    try {
      const { name, ...rest } = data
      await updateProfile(existingId, { name: name as string, ...rest })
      await refreshProfiles()
      toast.success(`Profile "${name}" replaced`)
      setImportConflict(null)
      navigate(`/profiles/${existingId}`)
    } catch {
      toast.error("Failed to replace profile.")
      setImportConflict(null)
    }
  }

  if (loading || profilesLoading) return <LoadingSpinner />

  if (profiles.length === 0) {
    return (
      <div>
        <PageHeader title="Dashboard" />
        <EmptyState
          icon={<LayoutDashboard className="h-10 w-10" />}
          title="Welcome to Stratoseer"
          description="Create your first profile or import an existing one to get started."
          actionLabel="Create Profile"
          onAction={() => setDialogOpen(true)}
        />
        <div className="flex justify-center mt-4">
          <Label
            htmlFor="dashboard-import"
            className="cursor-pointer inline-flex items-center gap-2 border rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
          >
            <Upload className="h-4 w-4" /> Import Profile
          </Label>
          <input id="dashboard-import" type="file" accept=".json" className="hidden" onChange={handleImport} />
        </div>
        <CreateProfileDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          name={newName}
          onNameChange={setNewName}
          onCreate={handleCreate}
        />
        <ImportConflictDialog
          conflict={importConflict}
          onCancel={() => setImportConflict(null)}
          onReplace={handleImportReplace}
        />
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Dashboard"
        actions={
          <div className="flex gap-2">
          <Label
            htmlFor="dashboard-import-main"
            className="cursor-pointer inline-flex items-center gap-2 border rounded-md px-3 py-2 text-sm hover:bg-accent transition-colors"
          >
            <Upload className="h-4 w-4" /> Import
          </Label>
          <input id="dashboard-import-main" type="file" accept=".json" className="hidden" onChange={handleImport} />
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                New Profile
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create Profile</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div className="grid gap-3">
                  <Label htmlFor="name">Profile Name</Label>
                  <Input
                    id="name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g. Project Manager"
                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  />
                </div>
                <Button onClick={handleCreate} className="w-full">
                  Create
                </Button>
              </div>
            </DialogContent>
          </Dialog>
          </div>
        }
      />

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-2 mb-8">
        <StatCard icon={<Users className="h-4 w-4" />} label="Profiles" value={profiles.length} />
        <StatCard icon={<Play className="h-4 w-4" />} label="Total Runs" value={runs.length} />
      </div>

      {/* Profile Cards */}
      <h2 className="text-lg font-semibold mb-3">Profiles</h2>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mb-8">
        {profiles.map((p) => (
          <Card
            key={p.id}
            className="cursor-pointer hover:border-primary/50 transition-colors"
            onClick={() => navigate(`/profiles/${p.id}`)}
          >
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{p.name}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1">
                {(p.skills ?? []).slice(0, 5).map((s) => (
                  <Badge key={s} variant="secondary" className="text-xs">
                    {s}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recent Runs */}
      <h2 className="text-lg font-semibold mb-3">Recent Runs</h2>
      {runs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No runs yet.</p>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run ID</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((r) => (
                <TableRow
                  key={r.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/profiles/${r.profile_id}/runs/${r.id}`)}
                >
                  <TableCell className="font-mono text-xs">{r.id.slice(0, 8)}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{r.mode}</Badge>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {r.started_at ? new Date(r.started_at).toLocaleString() : "-"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      <ImportConflictDialog
        conflict={importConflict}
        onCancel={() => setImportConflict(null)}
        onReplace={handleImportReplace}
      />
    </div>
  )
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode
  label: string
  value: string | number
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-primary">{icon}</span>
          <span className="text-muted-foreground">{label}</span>
        </div>
        <p className="text-2xl font-bold mt-1">{value}</p>
      </CardContent>
    </Card>
  )
}

function CreateProfileDialog({
  open,
  onOpenChange,
  name,
  onNameChange,
  onCreate,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  name: string
  onNameChange: (v: string) => void
  onCreate: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Profile</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div className="grid gap-3">
            <Label htmlFor="create-name">Profile Name</Label>
            <Input
              id="create-name"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder="e.g. Software Engineer"
              onKeyDown={(e) => e.key === "Enter" && onCreate()}
            />
          </div>
          <Button onClick={onCreate} className="w-full">
            Create
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ImportConflictDialog({
  conflict,
  onCancel,
  onReplace,
}: {
  conflict: { existingId: string; data: Record<string, unknown> } | null
  onCancel: () => void
  onReplace: () => void
}) {
  return (
    <AlertDialog open={!!conflict} onOpenChange={(open) => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Profile already exists</AlertDialogTitle>
          <AlertDialogDescription>
            A profile named "{String(conflict?.data?.name ?? "")}" already exists. Do you want to replace it with the imported data?
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onReplace}>Replace</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
