export type Company = {
  id: string
  name: string
  ticker: string | null
  market: string | null
  sort_order: number
  created_at: string
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
