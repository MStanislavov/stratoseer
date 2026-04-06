import { get } from "./client"
import type { PaginatedUsers } from "./types"

export function listUsers(page = 1, pageSize = 20) {
  return get<PaginatedUsers>(`/admin/users?page=${page}&page_size=${pageSize}`)
}
