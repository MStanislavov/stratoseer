import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { verifyEmail } from "@/api/auth"
import { useAuth } from "@/contexts/AuthContext"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token") || ""
  const { refreshUser } = useAuth()
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading")
  const [error, setError] = useState("")

  useEffect(() => {
    if (!token) {
      setStatus("error")
      setError("Missing verification token")
      return
    }

    verifyEmail(token)
      .then(() => {
        setStatus("success")
        refreshUser()
      })
      .catch((err) => {
        setStatus("error")
        setError(err instanceof Error ? err.message : "Verification failed")
      })
  }, [token, refreshUser])

  return (
    <div className="flex items-center justify-center min-h-screen bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl font-bold text-primary">Stratoseer</CardTitle>
          <CardDescription>Email Verification</CardDescription>
        </CardHeader>
        <CardContent className="text-center space-y-4">
          {status === "loading" && <LoadingSpinner />}
          {status === "success" && (
            <>
              <p className="text-sm text-muted-foreground">
                Your email has been verified successfully.
              </p>
              <Link to="/" className="text-primary hover:underline text-sm">
                Go to dashboard
              </Link>
            </>
          )}
          {status === "error" && (
            <>
              <p className="text-sm text-destructive">{error}</p>
              <Link to="/" className="text-primary hover:underline text-sm">
                Go to dashboard
              </Link>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
