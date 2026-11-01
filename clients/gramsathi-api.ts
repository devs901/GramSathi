/**
 * Typed client for the GramSathi Python API.
 * Works in the React admin (Vite) and the Expo / React Native app: plain fetch, no dependencies.
 *
 *   const api = new GramSathiApi('http://localhost:8000');
 *   await api.login('ramesh@example.com', 'Citizen@1234');
 *   const { items } = await api.myRation();
 *
 * In Vite use  new GramSathiApi(import.meta.env.VITE_API_URL)
 * In Expo use  new GramSathiApi(process.env.EXPO_PUBLIC_API_URL!)   (use your PC's LAN IP on a real phone, not localhost)
 */

export type Role = 'citizen' | 'admin';
export type DocStatus = 'pending' | 'approved' | 'rejected';
export type DocType = 'birth_certificate' | 'bonafide_certificate';
export type RozgarProfileType = 'worker' | 'employer';
export interface RozgarProfile { profile_type: RozgarProfileType; headline: string; skills: string[]; experience_years: number; education: string; location: string; bio: string; phone_public: boolean }
export interface RozgarJob { id: number; title: string; company: string; description: string; skills: string[]; location: string; job_type: string; salary_min: number | null; salary_max: number | null; status: string; match_score?: number; match_reason?: string; applied?: boolean }
export interface RozgarApplication { id: number; job_id: number; worker_id: number; status: string; match_score: number; match_reason: string; cover_note: string }

export interface User { id: number; name: string; email: string; mobile: string; age: number; role: Role; address: string; village: string }
export interface Session { token: string; user: User }
export interface AiReview { risk_score: number; risk_level: 'low' | 'medium' | 'high'; flags: string[]; recommendation: string; summary: string; source: 'claude' | 'rules' }
export interface DocumentRequest {
  id: number; user_id: number; doc_type: DocType; status: DocStatus; data: Record<string, string>;
  ai_review: AiReview | null; admin_note: string; created_at: string; reviewed_at: string | null;
  applicant_name?: string; applicant_email?: string;
}
export interface DocumentInput {
  doc_type: DocType; full_name: string; date_of_birth: string; father_name: string; mother_name?: string;
  address: string; place_of_birth?: string; purpose?: string; school_name?: string;
}
export interface RationCard { id: number; card_no: string; card_type: 'APL' | 'BPL' | 'AAY'; status: string; validity_start: string; validity_end: string; distribution_point: string; items: { name: string; quantity: number; unit: string }[] }
export interface NewsItem { id: number; title: string; description: string; title_hi: string; description_hi: string; title_mr: string; description_mr: string; category: string; priority: number; active: boolean; created_at: string }
export interface Center { id: number; name: string; address: string; phone: string; latitude: number; longitude: number; services: string[]; open_time: string; close_time: string; distance_km?: number }
export interface ChatReply { reply: string; source: 'claude' | 'rules' }
export interface ApiErrorBody { error: string; details?: { field: string; message: string }[] }

export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: ApiErrorBody['details']) { super(message); }
}

export class GramSathiApi {
  token: string | null = null;
  constructor(private baseUrl: string) {}

  private async request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
    const res = await fetch(this.baseUrl.replace(/\/$/, '') + '/api' + path, {
      method: init.method ?? 'GET',
      headers: { ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}) },
      body: init.body ? JSON.stringify(init.body) : undefined,
    });
    if (!res.ok) {
      const e = (await res.json().catch(() => ({ error: res.statusText }))) as ApiErrorBody;
      throw new ApiError(res.status, e.error, e.details);
    }
    return (await res.json()) as T;
  }

  // auth
  async login(email: string, password: string): Promise<Session> {
    const s = await this.request<Session>('/auth/login', { method: 'POST', body: { email, password } });
    this.token = s.token;
    return s;
  }
  async register(input: { name: string; email: string; mobile: string; age: number; password: string; village?: string; address?: string }): Promise<Session> {
    const s = await this.request<Session>('/auth/register', { method: 'POST', body: input });
    this.token = s.token;
    return s;
  }
  me = () => this.request<{ user: User }>('/auth/me');
  logout() { this.token = null; }

  // citizen
  myRation = () => this.request<{ items: RationCard[] }>('/me/ration');
  myWater = () => this.request<{ items: unknown[] }>('/me/water');
  myProperty = () => this.request<{ items: unknown[] }>('/me/property');
  payWaterBill = (id: number) => this.request<{ ok: boolean; simulated: boolean }>(`/me/water/bills/${id}/pay`, { method: 'POST' });
  payProperty = (id: number) => this.request<{ ok: boolean; simulated: boolean }>(`/me/property/${id}/pay`, { method: 'POST' });
  nearbyCenters = (lat?: number, lng?: number) => this.request<{ items: Center[] }>('/anganwadi' + (lat != null && lng != null ? `?lat=${lat}&lng=${lng}` : ''));
  news = (category?: string) => this.request<{ items: NewsItem[] }>('/news' + (category ? `?category=${category}` : ''));

  // documents
  requestDocument = (input: DocumentInput) => this.request<DocumentRequest>('/documents', { method: 'POST', body: input });
  myDocuments = () => this.request<{ items: DocumentRequest[] }>('/documents');
  /** Returns the approved certificate as a Blob (web). On React Native, fetch the URL with the auth header and save the file. */
  async downloadCertificate(id: number): Promise<Blob> {
    const res = await fetch(`${this.baseUrl.replace(/\/$/, '')}/api/documents/${id}/pdf`, { headers: { Authorization: `Bearer ${this.token}` } });
    if (!res.ok) throw new ApiError(res.status, ((await res.json().catch(() => ({ error: 'Download failed' }))) as ApiErrorBody).error);
    return res.blob();
  }

  // Rozgar marketplace
  rozgarProfile = () => this.request<{ profile: RozgarProfile | null }>('/rozgar/profile');
  saveRozgarProfile = (profile: RozgarProfile) => this.request<{ message: string }>('/rozgar/profile', { method: 'PUT', body: profile });
  rozgarJobs = (q = '', location = '') => this.request<{ items: RozgarJob[] }>(`/rozgar/jobs?q=${encodeURIComponent(q)}&location=${encodeURIComponent(location)}`);
  postRozgarJob = (job: Omit<RozgarJob, 'id' | 'status'>) => this.request<{ id: number; status: string; message: string }>('/rozgar/jobs', { method: 'POST', body: job });
  applyToRozgarJob = (id: number, cover_note = '') => this.request<{ id: number; match_score: number; match_reason: string }>(`/rozgar/jobs/${id}/apply`, { method: 'POST', body: { cover_note } });
  myRozgarApplications = () => this.request<{ items: RozgarApplication[] }>('/rozgar/applications/mine');
  myRozgarJobs = () => this.request<{ items: RozgarJob[] }>('/rozgar/jobs/mine');
  rozgarApplicants = (jobId: number) => this.request<{ items: unknown[] }>(`/rozgar/jobs/${jobId}/applicants`);
  updateRozgarApplication = (id: number, status: 'shortlisted' | 'rejected' | 'hired') => this.request<{ message: string }>(`/rozgar/applications/${id}`, { method: 'PATCH', body: { status } });
  draftRozgarProfile = (input: { skills: string[]; education: string; experience: string; target_role: string }) => this.request<{ headline: string; bio: string; source: string }>('/ai/rozgar/profile-draft', { method: 'POST', body: input });
  draftRozgarJob = (notes: string) => this.request<{ title: string; description: string; skills: string[]; source: string }>('/ai/rozgar/job-draft', { method: 'POST', body: { notes } });
  draftRozgarCoverNote = (input: { job_title: string; company: string; skills: string[]; experience: string }) => this.request<{ cover_note: string; source: string }>('/ai/rozgar/cover-draft', { method: 'POST', body: input });

  // AI
  chat = (message: string, language: 'en' | 'hi' | 'mr' = 'en') => this.request<ChatReply>('/ai/chat', { method: 'POST', body: { message, language } });

  // admin
  dashboard = () => this.request<Record<string, unknown>>('/admin/dashboard');
  reviewDocument = (id: number, decision: 'approved' | 'rejected', note = '') => this.request<DocumentRequest>(`/documents/${id}/review`, { method: 'POST', body: { decision, note } });
  draftNews = (points: string) => this.request<Partial<NewsItem> & { source: 'claude' | 'rules' }>('/ai/news-draft', { method: 'POST', body: { points } });
}
