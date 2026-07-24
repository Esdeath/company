export type Identifier = string
export type Timestamp = string

export type User = {
  id: Identifier
  email: string
  username: string
  email_verified_at: Timestamp | null
  first_comment_approved_at: Timestamp | null
  reply_email_enabled: boolean
}

export type UserAuthState = {
  authenticated: boolean
  user: User | null
  csrf_token: string | null
  expires_at: Timestamp | null
  registration_enabled: boolean
}

export type MessageResponse = {
  message: string
}

export type RegisterInput = {
  email: string
  username: string
  password: string
}

export type LoginInput = {
  email: string
  password: string
}

export type VerifyEmailInput = {
  token: string
}

export type PasswordResetRequestInput = {
  email: string
}

export type PasswordResetConfirmInput = {
  token: string
  password: string
}

export type ProfileUpdateInput = {
  username: string
}

export type PasswordUpdateInput = {
  current_password: string
  password: string
}

export type PreferencesUpdateInput = {
  reply_email_enabled: boolean
}

export type AccountDeleteInput = {
  password: string
}

export type CommentStatus = 'pending' | 'published' | 'rejected' | 'deleted'

export type CommentAuthor = {
  id: Identifier | null
  username: string
}

export type Comment = {
  id: Identifier
  document_id: Identifier
  parent_id: Identifier | null
  body: string | null
  status: CommentStatus
  author: CommentAuthor
  created_at: Timestamp
  edited_at: Timestamp | null
  replies: Comment[]
  can_edit: boolean
  can_delete: boolean
  can_report: boolean
}

export type CommentPage = {
  items: Comment[]
  viewer_pending: Comment[]
  next_cursor: string | null
  total_count: number
}

export type CommentThread = {
  root: Comment
  target_comment_id: Identifier
  viewer_pending: Comment[]
}

export type CommentCreateInput = {
  body: string
  parent_id?: Identifier | null
}

export type CommentUpdateInput = {
  body: string
}

export type CommentReportInput = {
  reason: string
  details?: string | null
}

export type ReportStatus = 'open' | 'kept' | 'removed'

export type CommentReport = {
  id: Identifier
  comment_id: Identifier
  reporter_id: Identifier
  reporter_username: string
  reason: string
  details: string | null
  status: ReportStatus
  created_at: Timestamp
  resolved_at: Timestamp | null
  resolved_by: string | null
}

export type NotificationType = 'reply' | 'comment_approved' | 'comment_rejected'

export type Notification = {
  id: Identifier
  type: NotificationType
  company_id: Identifier
  document_id: Identifier
  comment_id: Identifier
  actor_username: string | null
  excerpt: string
  message: string
  created_at: Timestamp
  read_at: Timestamp | null
}

export type NotificationPage = {
  items: Notification[]
  unread_count: number
}

export type CursorPage<T> = {
  items: T[]
  next_cursor: string | null
}
