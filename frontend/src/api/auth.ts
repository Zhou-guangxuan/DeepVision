import { http } from './client'

export interface User {
  id: number
  username: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export async function register(username: string, password: string): Promise<User> {
  const { data } = await http.post<User>(
    '/api/auth/register',
    { username, password },
    { silent: true },
  )
  return data
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>(
    '/api/auth/login',
    { username, password },
    { silent: true },
  )
  return data
}

export async function fetchMe(): Promise<User> {
  const { data } = await http.get<User>('/api/auth/me')
  return data
}
