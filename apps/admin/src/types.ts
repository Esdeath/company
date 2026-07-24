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

export type AdminSection = 'documents' | 'comments' | 'users'

export type CommentStatus = 'pending' | 'published' | 'rejected' | 'deleted'

export type ReportStatus = 'open' | 'kept' | 'removed'

export type UserStatus = 'pending_verification' | 'active' | 'suspended'

export type ModerationComment = {
  id: string
  document_id: string
  document_title: string
  author_id: string | null
  author_username: string | null
  parent_id: string | null
  body: string | null
  status: CommentStatus
  created_at: string
  edited_at: string | null
  moderated_at: string | null
  deleted_at: string | null
  moderation_reason: string | null
  moderated_by: string | null
}

export type ModerationCommentPage = {
  items: ModerationComment[]
  next_cursor: string | null
}

export type ModerationReport = {
  id: string
  comment_id: string
  reporter_id: string
  reporter_username: string
  reason: string
  details: string | null
  status: ReportStatus
  created_at: string
  resolved_at: string | null
  resolved_by: string | null
  comment: ModerationComment
}

export type ModerationReportPage = {
  items: ModerationReport[]
  next_cursor: string | null
}

export type ModerationUser = {
  id: string
  email: string
  username: string
  status: UserStatus
  email_verified_at: string | null
  first_comment_approved_at: string | null
  created_at: string
  comment_count: number
}

export type ModerationUserPage = {
  items: ModerationUser[]
  next_cursor: string | null
}
