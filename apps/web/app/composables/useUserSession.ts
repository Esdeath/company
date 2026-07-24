import { computed, ref } from 'vue'

import {
  confirmPasswordReset,
  getUserSession,
  isUserAuthenticationRequired,
  loginUser,
  logoutUser,
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
  UserAuthState,
  VerifyEmailInput,
} from '../types/community'

const state = ref<UserAuthState | null>(null)
const loading = ref(false)
let restoring: Promise<UserAuthState> | null = null

function anonymousState(): UserAuthState {
  return {
    authenticated: false,
    user: null,
    csrf_token: null,
    expires_at: null,
    registration_enabled: state.value?.registration_enabled ?? false,
  }
}

function remember(next: UserAuthState): UserAuthState {
  state.value = next
  return next
}

function clearAfterAuthenticationFailure(error: unknown): void {
  if (isUserAuthenticationRequired(error)) state.value = anonymousState()
}

export function useUserSession() {
  const user = computed(() => state.value?.user ?? null)
  const authenticated = computed(() => state.value?.authenticated === true)

  async function restore(): Promise<UserAuthState> {
    if (restoring) return restoring

    loading.value = true
    restoring = getUserSession()
      .then(remember)
      .catch((error: unknown) => {
        clearAfterAuthenticationFailure(error)
        throw error
      })
      .finally(() => {
        loading.value = false
        restoring = null
      })

    return restoring
  }

  async function register(input: RegisterInput): Promise<MessageResponse> {
    try {
      return await registerUser(input)
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function verifyEmail(input: VerifyEmailInput): Promise<UserAuthState> {
    try {
      return remember(await verifyEmailRequest(input))
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function login(input: LoginInput): Promise<UserAuthState> {
    try {
      return remember(await loginUser(input))
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    }
  }

  async function logout(): Promise<void> {
    try {
      await logoutUser()
    } catch (error) {
      clearAfterAuthenticationFailure(error)
      throw error
    } finally {
      state.value = anonymousState()
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
    try {
      return remember(await confirmPasswordReset(input))
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
  }
}
