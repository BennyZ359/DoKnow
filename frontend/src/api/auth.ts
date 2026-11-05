import { http } from './client'
import type {
  AuthResponse,
  LoginRequest,
  MeResponse,
  ProfileUpdate,
  RegisterRequest,
} from './types'

/** /auth — register, login, logout, profile (§ API 层只做鉴权与转发). */
export const authApi = {
  register: (body: RegisterRequest) => http.post<AuthResponse>('/auth/register', body),
  login: (body: LoginRequest) => http.post<AuthResponse>('/auth/login', body),
  logout: () => http.post<{ ok: boolean }>('/auth/logout'),
  me: () => http.get<MeResponse>('/auth/me'),
  updateMe: (patch: ProfileUpdate) => http.patch<MeResponse>('/auth/me', patch),
}
