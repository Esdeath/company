import { computed, ref } from 'vue'

import {
  confirmPasswordReset,
  getUserSession,
  isUserAuthenticationRequired,
  loginUser,
  logoutUser,
  onUserAuthenticationRequired,
  registerUser,
  requestPasswordReset,
  verifyEmail as verifyEmailRequest,
} from '../api/community'
import type {
  LoginInput,
  MessageResponse,
  PasswordResetConfirmInput,
  PasswordResetRequestInput,
  RegisterInput,
  User,
  UserAuthState,
  VerifyEmailInput,
} from '../types/community'

const state = ref<UserAuthState | null>(null)
const loading = ref(false)
let sessionGeneration = 0
let activeRestores = 0
let restoring: { generation: number; promise: Promise<UserAuthState> } | null = null

function anonymousState(): UserAuthState {
  return {
    authenticated: false,
    user: null,
    csrf_token: null,
    expires_at: null,
    registration_enabled: state.value?.registration_enabled ?? false,
  }
}

function replaceState(next: UserAuthState): UserAuthState {
  sessionGeneration += 1
  state.value = next
  return next
}

function replaceUser(user: User): UserAuthState | null {
  sessionGeneration += 1
  if (!state.value) return null
  state.value = { ...state.value, authenticated: true, user }
  return state.value
}

function invalidateRestore() {
  sessionGeneration += 1
}

function clearSession(): UserAuthState {
  return replaceState(anonymousState())
}

function clearAfterAuthenticationFailure(error: unknown): void {
  if (isUserAuthenticationRequired(error)) clearSession()
}

onUserAuthenticationRequired(() => {
  clearSession()
})

export function useUserSession() {
  const user = computed(() => state.value?.user ?? null)
  const authenticated = computed(() => state.value?.authenticated === true)

  async function restore(): Promise<UserAuthState> {
    const requestGeneration = sessionGeneration
    if (restoring?.generation === requestGeneration) return restoring.promise

    activeRestores += 1
    loading.value = true
    const promise = getUserSession()
      .then((next) => {
        if (sessionGeneration !== requestGeneration) return state.value ?? anonymousState()
        return replaceState(next)
      })
      .catch((error: unknown) => {
        if (sessionGeneration === requestGeneration) clearAfterAuthenticationFailure(error)
        throw error
      })
      .finally(() => {
        activeRestores -= 1
        loading.value = activeRestores > 0
        if (restoring?.promise === promise) restoring = null
      })

    restoring = { generation: requestGeneration, promise }
    return promise
  }

  async function register(input: RegisterInput): Promise<MessageResponse> {
    invalidateRestore()
    try {
      return await registerUser(input)
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function verifyEmail(input: VerifyEmailInput): Promise<UserAuthState> {
    invalidateRestore()
    try {
      return replaceState(await verifyEmailRequest(input))
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function login(input: LoginInput): Promise<UserAuthState> {
    invalidateRestore()
    try {
      return replaceState(await loginUser(input))
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function logout(): Promise<void> {
    invalidateRestore()
    try {
      await logoutUser()
      clearSession()
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function requestReset(input: PasswordResetRequestInput): Promise<MessageResponse> {
    try {
      return await requestPasswordReset(input)
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function confirmReset(input: PasswordResetConfirmInput): Promise<UserAuthState> {
    invalidateRestore()
    try {
      return replaceState(await confirmPasswordReset(input))
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function requireLogin(): Promise<boolean> {
    if (authenticated.value) return true
    if (!state.value) await restore()
    return authenticated.value
  }

  return {
    state,
    user,
    authenticated,
    loading,
    restore,
    register,
    verifyEmail,
    login,
    logout,
    requestReset,
    confirmReset,
    requireLogin,
    replaceState,
    replaceUser,
  }
}
