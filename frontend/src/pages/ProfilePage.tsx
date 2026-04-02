import { useEffect, useState, useCallback, useRef } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { Save, Trash2, Upload, Download, X, Plus, Play, Briefcase, FileEdit, Sparkles } from "lucide-react"
import { getProfile, updateProfile, deleteProfile, uploadCv, extractSkillsFromCv, exportProfile, createProfile } from "@/api/profiles"
import type { Profile, ProfileUpdate } from "@/api/types"
import { useProfiles } from "@/contexts/ProfileContext"
import { PageHeader } from "@/components/shared/PageHeader"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { toast } from "sonner"

export default function ProfilePage() {
  const { profileId } = useParams()
  const navigate = useNavigate()
  const { refresh: refreshProfiles } = useProfiles()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)

  const [name, setName] = useState("")
  const [targets, setTargets] = useState<string[]>([])
  const [constraints, setConstraints] = useState<string[]>([])
  const [skills, setSkills] = useState<string[]>([])

  const draftKey = profileId ? `profile-draft-${profileId}` : null

  const load = useCallback(() => {
    if (!profileId || !draftKey) return
    getProfile(profileId)
      .then((p) => {
        setProfile(p)
        const raw = localStorage.getItem(draftKey)
        if (raw) {
          try {
            const draft = JSON.parse(raw)
            setName(draft.name ?? p.name)
            setTargets(draft.targets ?? p.targets ?? [])
            setConstraints(draft.constraints ?? p.constraints ?? [])
            setSkills(draft.skills ?? p.skills ?? [])
            return
          } catch { /* ignore corrupt draft */ }
        }
        setName(p.name)
        setTargets(p.targets ?? [])
        setConstraints(p.constraints ?? [])
        setSkills(p.skills ?? [])
      })
      .finally(() => setLoading(false))
  }, [profileId, draftKey])

  useEffect(() => { load() }, [load])

  // Persist draft to localStorage on changes
  const dirtyRef = useRef(false)
  useEffect(() => {
    if (!draftKey || !profile) return
    const draft = { name, targets, constraints, skills }
    const saved = { name: profile.name, targets: profile.targets ?? [], constraints: profile.constraints ?? [], skills: profile.skills ?? [] }
    const dirty = JSON.stringify(draft) !== JSON.stringify(saved)
    dirtyRef.current = dirty
    if (dirty) {
      localStorage.setItem(draftKey, JSON.stringify(draft))
    } else {
      localStorage.removeItem(draftKey)
    }
  }, [draftKey, name, targets, constraints, skills, profile])

  // Warn on navigation away with unsaved changes
  useEffect(() => {
    return () => {
      if (dirtyRef.current) {
        toast.warning("You have unsaved profile changes. Your draft has been saved.")
      }
    }
  }, [profileId])

  function canSave() {
    return targets.length > 0 && skills.length > 0 && !!profile?.cv_path
  }

  async function handleSave() {
    if (!profileId) return
    if (!canSave()) {
      const missing: string[] = []
      if (targets.length === 0) missing.push("career goals")
      if (skills.length === 0) missing.push("skills")
      if (!profile?.cv_path) missing.push("a CV")
      toast.error(`Please add ${missing.join(", ")} before saving`)
      return
    }
    const data: ProfileUpdate = { name, targets, constraints, skills }
    const updated = await updateProfile(profileId, data)
    setProfile(updated)
    if (draftKey) localStorage.removeItem(draftKey)
    await refreshProfiles()
    toast.success("Profile saved")
  }

  async function handleDelete() {
    if (!profileId) return
    await deleteProfile(profileId)
    if (draftKey) localStorage.removeItem(draftKey)
    await refreshProfiles()
    toast.success("Profile deleted")
    navigate("/")
  }

  async function handleCvUpload(e: React.ChangeEvent<HTMLInputElement>) {
    if (!profileId || !e.target.files?.[0]) return
    const updated = await uploadCv(profileId, e.target.files[0])
    setProfile(updated)
    toast.success("CV uploaded")
  }

  const [extracting, setExtracting] = useState(false)

  async function handleExtractSkills() {
    if (!profileId) return
    setExtracting(true)
    try {
      const { skills: extracted } = await extractSkillsFromCv(profileId)
      const merged = [...new Set([...skills, ...extracted])]
      setSkills(merged)
      toast.success(`Imported ${extracted.length} skills from CV`)
    } catch {
      toast.error("Failed to extract skills from CV")
    } finally {
      setExtracting(false)
    }
  }

  async function handleExport() {
    if (!profileId) return
    const data = await exportProfile(profileId)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${profile?.name ?? "profile"}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast.success("Profile exported")
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const created = await createProfile(data)
      await refreshProfiles()
      toast.success(`Profile "${created.name}" imported`)
      navigate(`/profiles/${created.id}`)
    } catch {
      toast.error("Failed to import profile. Check the file format.")
    }
    e.target.value = ""
  }

  if (loading) return <LoadingSpinner />
  if (!profile) return <p className="text-muted-foreground">Profile not found.</p>

  return (
    <div>
      <PageHeader
        title={profile.name}
        description={`Created ${new Date(profile.created_at).toLocaleDateString()}`}
        actions={
          <div className="flex gap-2">
            <Button onClick={handleSave} disabled={!canSave()}>
              <Save className="h-4 w-4 mr-2" /> Save
            </Button>
            <Button variant="outline" onClick={handleExport}>
              <Download className="h-4 w-4 mr-2" /> Export
            </Button>
            <Label
              htmlFor="profile-import"
              className="cursor-pointer inline-flex items-center gap-2 border rounded-md px-3 py-2 text-sm hover:bg-accent transition-colors"
            >
              <Upload className="h-4 w-4" /> Import
            </Label>
            <input id="profile-import" type="file" accept=".json" className="hidden" onChange={handleImport} />
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive">
                  <Trash2 className="h-4 w-4 mr-2" /> Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete profile?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete "{profile.name}" and all associated data.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Name */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Name</CardTitle>
          </CardHeader>
          <CardContent>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </CardContent>
        </Card>

        {/* CV Upload */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">CV</CardTitle>
          </CardHeader>
          <CardContent>
            {profile.cv_path ? (
              <p className="text-sm text-muted-foreground mb-2">
                Uploaded: {profile.cv_path.split("/").pop()}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground mb-2">No CV uploaded</p>
            )}
            <div className="flex gap-2">
              <Label
                htmlFor="cv-upload"
                className="cursor-pointer inline-flex items-center gap-2 border rounded-md px-3 py-2 text-sm hover:bg-accent transition-colors"
              >
                <Upload className="h-4 w-4" /> Upload CV
              </Label>
              <input id="cv-upload" type="file" className="hidden" onChange={handleCvUpload} />
              {profile.cv_path && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExtractSkills}
                  disabled={extracting}
                >
                  <Sparkles className="h-4 w-4 mr-2" />
                  {extracting ? "Extracting..." : "Import Skills from CV"}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Tag lists */}
        <TagCard
          label="Career Goals"
          items={targets}
          onChange={setTargets}
          placeholder="e.g. Find a software engineering job / Obtain an AI certificate / Join communities"
          examples={["Move into a leadership position", "Earn a professional certification", "Transition to a new industry", "Grow my professional network"]}
        />
        <TagCard
          label="Constraints"
          items={constraints}
          onChange={setConstraints}
          placeholder="e.g. Remote only, EU timezone"
          examples={["Remote only", "No relocation", "Part-time or flexible hours", "Within commuting distance"]}
        />
        <TagCard label="Skills" items={skills} onChange={setSkills} />

        {/* Quick actions */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Quick Actions</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button variant="outline" asChild>
              <Link to={`/profiles/${profileId}/runs`}>
                <Play className="h-4 w-4 mr-2" /> Runs
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to={`/profiles/${profileId}/results`}>
                <Briefcase className="h-4 w-4 mr-2" /> Results
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to={`/profiles/${profileId}/cover-letters`}>
                <FileEdit className="h-4 w-4 mr-2" /> Cover Letters
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function TagCard({
  label,
  items,
  onChange,
  placeholder,
  examples,
}: {
  label: string
  items: string[]
  onChange: (v: string[]) => void
  placeholder?: string
  examples?: string[]
}) {
  const [input, setInput] = useState("")

  function add() {
    const val = input.trim()
    if (val && !items.includes(val)) {
      onChange([...items, val])
    }
    setInput("")
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1 mb-2">
          {items.map((item) => (
            <Badge key={item} variant="secondary" className="gap-1">
              {item}
              <button onClick={() => onChange(items.filter((i) => i !== item))}>
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={placeholder ?? `Add ${label.toLowerCase()}...`}
            onKeyDown={(e) => e.key === "Enter" && add()}
            className="flex-1"
          />
          <Button variant="outline" size="icon" onClick={() => add()}>
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        {examples && items.length === 0 && (
          <div className="mt-3">
            <p className="text-xs text-muted-foreground mb-1.5">Examples:</p>
            <div className="flex flex-wrap gap-1">
              {examples.map((ex) => (
                <Badge key={ex} variant="outline" className="text-muted-foreground">
                  {ex}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
