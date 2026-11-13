// One function per backend endpoint — thin, typed, no business logic.
import { get, post } from './client';
import type {
  Application,
  Candidate,
  CandidateSkill,
  Department,
  Feedback,
  FunnelReport,
  AnomalySummary,
  Interview,
  Interviewer,
  AvailabilitySlot,
  Offer,
  Page,
  Requisition,
  ResumeArtifact,
  ScreeningRun,
  SubmissionAttempt,
  SystemActor,
} from '../types/api';

// --- Reference data ---
export const listDepartments = () => get<Department[]>('/api/v1/departments');
export const listActors = () => get<SystemActor[]>('/api/v1/actors');
export const listInterviewers = () => get<Interviewer[]>('/api/v1/interviewers');

// --- Requisitions ---
export const listRequisitions = (params?: { status?: string; department_id?: string; limit?: number; offset?: number }) =>
  get<Page<Requisition>>('/api/v1/requisitions', params);
export const getRequisition = (id: string) => get<Requisition>(`/api/v1/requisitions/${id}`);
export const transitionRequisition = (
  id: string,
  body: { to_status: string; actor_id: string; reason_text?: string },
) => post<Requisition>(`/api/v1/requisitions/${id}/transition`, body);

// --- Candidates ---
export const listCandidates = (params?: { search?: string; limit?: number; offset?: number }) =>
  get<Page<Candidate>>('/api/v1/candidates', params);
export const getCandidate = (id: string) => get<Candidate>(`/api/v1/candidates/${id}`);
export const getCandidateSkills = (id: string) => get<CandidateSkill[]>(`/api/v1/candidates/${id}/skills`);
export const getCandidateResumes = (id: string) => get<ResumeArtifact[]>(`/api/v1/candidates/${id}/resumes`);

// --- Applications ---
export const listApplications = (params?: {
  requisition_id?: string;
  candidate_id?: string;
  stage?: string;
  limit?: number;
  offset?: number;
}) => get<Page<Application>>('/api/v1/applications', params);
export const getApplication = (id: string) => get<Application>(`/api/v1/applications/${id}`);
export const getApplicationScreeningRuns = (id: string) =>
  get<ScreeningRun[]>(`/api/v1/applications/${id}/screening-runs`);
export const getApplicationAttempts = (id: string) =>
  get<SubmissionAttempt[]>(`/api/v1/applications/${id}/attempts`);
export const submitApplication = (body: { candidate_id: string; requisition_id: string }) =>
  post<Application>('/api/v1/applications', body);
export const screenApplication = (id: string) => post<Application>(`/api/v1/applications/${id}/screen`);
export const transitionApplication = (
  id: string,
  body: { to_stage: string; actor_id: string; reason_text?: string; rejected_reason?: string },
) => post<Application>(`/api/v1/applications/${id}/transition`, body);

// --- Interviews ---
export const listInterviews = (params?: {
  application_id?: string;
  interviewer_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}) => get<Page<Interview>>('/api/v1/interviews', params);
export const getInterview = (id: string) => get<Interview>(`/api/v1/interviews/${id}`);
export const getInterviewFeedback = (id: string) => get<Feedback | null>(`/api/v1/interviews/${id}/feedback`);
export const scheduleInterview = (body: {
  application_id: string;
  interviewer_id: string;
  round_type: string;
  scheduled_start: string;
  scheduled_end: string;
  location_mode?: string;
}) => post<Interview>('/api/v1/interviews', body);
export const transitionInterviewStatus = (id: string, to_status: string) =>
  post<Interview>(`/api/v1/interviews/${id}/status`, { to_status });
export const submitFeedback = (
  id: string,
  body: {
    interviewer_id: string;
    recommendation: string;
    overall_score: number;
    submitted_at: string;
    strengths_text?: string;
    concerns_text?: string;
  },
) => post<Feedback>(`/api/v1/interviews/${id}/feedback`, body);
export const getInterviewerAvailability = (interviewerId: string) =>
  get<AvailabilitySlot[]>(`/api/v1/interviews/availability/${interviewerId}`);

// --- Offers ---
export const listOffers = (params?: { status?: string; application_id?: string; limit?: number; offset?: number }) =>
  get<Page<Offer>>('/api/v1/offers', params);
export const getOffer = (id: string) => get<Offer>(`/api/v1/offers/${id}`);
export const createOffer = (body: { application_id: string; proposed_salary: number; currency?: string; equity_amount?: number }) =>
  post<Offer>('/api/v1/offers', body);
export const transitionOffer = (
  id: string,
  body: { to_status: string; actor_id: string; reason_text?: string; expiry_date?: string },
) => post<Offer>(`/api/v1/offers/${id}/transition`, body);

// --- Analytics ---
export const getFunnelReport = () => get<FunnelReport>('/api/v1/analytics/funnel');
export const getAnomalySummary = () => get<AnomalySummary>('/api/v1/analytics/anomaly-summary');
