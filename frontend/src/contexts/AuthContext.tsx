import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react"
import type { UserRead } from "@/api/types"
import type { LoginData, RegisterData } from "@/api/auth"
import * as authApi from "@/api/auth"
import { setTokens, clearTokens, getAccessToken } from "@/api/client"

interface AuthContextValue {
  user: UserRead | null
  loading: boolean
  login: (data: LoginData) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    try {
      const u = await authApi.getMe()
      setUser(u)
    } catch {
      setUser(null)
      clearTokens()
    }
  }, [])

  useEffect(() => {
    const token = getAccessToken()
    if (token) {
      refreshUser().finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [refreshUser])

  const login = useCallback(async (data: LoginData) => {
    const resp = await authApi.login(data)
    setTokens(resp.access_token, resp.refresh_token)
    setUser(resp.user)
  }, [])

  const register = useCallback(async (data: RegisterData) => {
    const resp = await authApi.register(data)
    setTokens(resp.access_token, resp.refresh_token)
    setUser(resp.user)
  }, [])

  const logout = useCallback(async () => {
    const rt = localStorage.getItem("refresh_token")
    if (rt) {
      try {
        await authApi.logout(rt)
      } catch {
        // ignore
      }
    }
    clearTokens()
    setUser(null)
  }, [])

  const isAdmin = user?.role === "admin"

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser, isAdmin }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
