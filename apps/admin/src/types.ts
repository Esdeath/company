export type Company = {
  id: string
  name: string
  ticker: string | null
  market: string | null
}

export type CompanyInput = {
  name: string
  ticker: string | null
  market: string | null
}

export type DocumentFormat = 'html' | 'markdown'

export type DocumentItem = {
  id: string
  company_id: string
  title: string
  format: DocumentFormat
  original_filename: string
  sort_order: number
  uploaded_at: string
  content_url: string
}

export type UploadItem = {
  id: string
  title: string
  format: DocumentFormat
  content_url: string
}

export type UploadError = {
  filename: string
  message: string
}

export type UploadBatch = {
  items: UploadItem[]
  errors: UploadError[]
}

export type AuthState = {
  authenticated: boolean
  username: string | null
  csrf_token: string
  expires_at: string | null
}

export type LoginInput = {
  username: string
  password: string
}
