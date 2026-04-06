import { useEffect, useRef, useState } from "react"
import type { SSEEvent } from "@/api/types"
import { getAccessToken } from "@/api/client"

const TERMINAL_TYPES = new Set(["run_finished", "run_failed", "run_cancelled"])

export function useSSE(profileId: string | undefined, runId: string | undefined) {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [done, setDone] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!profileId || !runId) return

    const token = getAccessToken()
    const url = `/api/profiles/${profileId}/runs/${runId}/stream${token ? `?token=${encodeURIComponent(token)}` : ""}`
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => setConnected(true)

    es.onmessage = (msg) => {
      try {
        const event: SSEEvent = JSON.parse(msg.data)
        setEvents((prev) => [...prev, event])
        if (TERMINAL_TYPES.has(event.type)) {
          setDone(true)
          es.close()
        }
      } catch {
        // ignore unparseable messages
      }
    }

    es.onerror = () => {
      setConnected(false)
      setDone(true)
      es.close()
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [profileId, runId])

  return { events, connected, done }
}
