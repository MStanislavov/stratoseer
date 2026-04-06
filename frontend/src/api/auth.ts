import { post, get } from "./client"
import type { TokenResponse, UserRead } from "./types"

export interface RegisterData {
  first_name: string
  last_name: string
  email: string
  password: string
}

export interface LoginData {
  email: string
  password: string
}

export function register(data: RegisterData) {
  return post<TokenResponse>("/auth/register", data)
}

export function login(data: LoginData) {
  return post<TokenResponse>("/auth/login", data)
}

export function refreshToken(refresh_token: string) {
  return post<{ access_token: string; refresh_token: string; token_type: string }>(
    "/auth/refresh",
    { refresh_token },
  )
}

export function logout(refresh_token: string) {
  return post<{ detail: string }>("/auth/logout", { refresh_token })
}

export function getMe() {
  return get<UserRead>("/auth/me")
}

export function verifyEmail(token: string) {
  return post<{ detail: string }>("/auth/verify-email", { token })
}

export function forgotPassword(email: string) {
  return post<{ detail: string }>("/auth/forgot-password", { email })
}

export function resetPassword(token: string, password: string) {
  return post<{ detail: string }>("/auth/reset-password", { token, password })
}
