// Typed API contracts — mirrors backend/app/schemas/*.py field-for-field.
// This is the only place entity shapes are defined; pages/components
// import from here rather than redeclaring fields.

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    field: string | null;
  };
}

export interface Department {
  department_id: string;
  name: string;
  cost_center_code: string;
}

export interface SystemActor {
  actor_id: string;
  full_name: string;
  role: 'BUSINESS_REQUESTER' | 'PROCESS_OWNER' | 'APPROVER' | 'OPERATIONS_ANALYST' | 'SYSTEM_ADMINISTRATOR';
  department_id: string | null;
  email: string;
  is_active: boolean;
}

export interface Interviewer {
  interviewer_id: string;
  full_name: string;
  email: string;
  department_id: string;
  title: string;
  is_active: boolean;
}

export interface AvailabilitySlot {
  slot_id: string;
  interviewer_id: string;
  start_datetime: string;
  end_datetime: string;
  is_booked: boolean;
}

export type RequisitionStatus =
  | 'Draft'
  | 'PendingApproval'
  | 'Approved'
  | 'Open'
  | 'OnHold'
  | 'Closed'
  | 'Cancelled';

export interface Requisition {
  requisition_id: string;
  department_id: string;
  title: string;
  level: string;
  employment_type: string;
  status: RequisitionStatus;
  salary_min: number;
  salary_max: number;
  headcount: number;
  requested_by_actor_id: string;
  opened_at: string | null;
  target_close_date: string | null;
  closed_at: string | null;
  created_at: string;
}

export interface Candidate {
  candidate_id: string;
  full_name: string;
  email: string;
  phone: string | null;
  location_city: string;
  location_country: string;
  years_experience: number;
  highest_education_level: string;
  source_channel: string;
  created_at: string;
}

export interface CandidateSkill {
  skill_id: string;
  skill_name: string;
  proficiency_level: string;
  years_of_experience: number;
  source: string;
}

export interface ResumeArtifact {
  resume_artifact_id: string;
  file_name: string;
  file_format: string;
  parsed_years_experience: number;
  parsed_education_level: string;
  is_latest: boolean;
  uploaded_at: string;
}

export type ApplicationStage =
  | 'Applied'
  | 'Screening'
  | 'Interviewing'
  | 'Offer'
  | 'Hired'
  | 'Rejected'
  | 'Withdrawn';

export interface Application {
  application_id: string;
  candidate_id: string;
  requisition_id: string;
  resume_artifact_id: string;
  applied_at: string;
  source_channel: string;
  stage: ApplicationStage;
  screening_score: number | null;
  screening_skill_component: number | null;
  screening_experience_component: number | null;
  screening_education_component: number | null;
  screening_education_gate_passed: boolean | null;
  screening_decision: 'Pass' | 'Fail' | null;
  screening_rule_version: number | null;
  screening_computed_at: string | null;
  screening_explanation: string | null;
  latest_screening_run_id: string | null;
  rejected_reason: string | null;
  withdrawn_at: string | null;
  created_at: string;
  updated_at: string;
  candidate_name?: string | null;
  requisition_title?: string | null;
}

export interface ScreeningRun {
  screening_run_id: string;
  application_id: string;
  screening_rule_id: string;
  is_latest: boolean;
  screening_rule_version: number;
  screening_skill_component: number;
  screening_experience_component: number;
  screening_education_component: number;
  screening_education_gate_passed: boolean;
  screening_score: number;
  screening_decision: 'Pass' | 'Fail';
  screening_explanation: string;
  computed_at: string;
}

export interface SubmissionAttempt {
  attempt_id: string;
  canonical_application_id: string;
  candidate_id: string;
  requisition_id: string;
  submitted_at: string;
  is_canonical: boolean;
  duplicate_of_attempt_id: string | null;
  issue_type: 'None' | 'DuplicateSubmission';
}

export type InterviewStatus = 'Scheduled' | 'Completed' | 'Cancelled' | 'NoShow';

export interface Interview {
  interview_id: string;
  application_id: string;
  interviewer_id: string;
  round_number: number;
  round_type: string;
  scheduled_start: string;
  scheduled_end: string;
  status: InterviewStatus;
  location_mode: string;
  created_at: string;
  updated_at: string;
}

export interface Feedback {
  feedback_id: string;
  interview_id: string;
  interviewer_id: string;
  recommendation: 'StrongYes' | 'Yes' | 'No' | 'StrongNo';
  overall_score: number;
  strengths_text: string | null;
  concerns_text: string | null;
  submitted_at: string;
}

export type OfferStatus =
  | 'Drafted'
  | 'PendingApproval'
  | 'Approved'
  | 'Extended'
  | 'Accepted'
  | 'Declined'
  | 'Rescinded'
  | 'Expired';

export interface Offer {
  offer_id: string;
  application_id: string;
  proposed_salary: number;
  currency: string;
  equity_amount: number | null;
  status: OfferStatus;
  approved_by_actor_id: string | null;
  approved_at: string | null;
  extended_at: string | null;
  decision_at: string | null;
  expiry_date: string | null;
  created_at: string;
}

export interface FunnelGroupRow {
  group_by: string | null;
  group_key: string;
  reached_counts: Record<string, number>;
  conversion_rates: Record<string, number | null>;
}

export interface OfferAcceptanceRow {
  group_by: string | null;
  group_key: string;
  accepted_count: number;
  extended_count: number;
  acceptance_rate: number | null;
}

export interface DuplicateSubmissionRow {
  group_by: string;
  group_key: string;
  attempt_count: number;
  canonical_application_count: number;
  attempts_per_application: number | null;
}

export interface InterviewerLoadRow {
  interviewer_id: string;
  iso_year: number;
  iso_week: number;
  interview_count: number;
  availability_slot_count: number;
  load_ratio: number | null;
}

export interface RequisitionStatusDistributionRow {
  status: string;
  count: number;
}

export interface FunnelReport {
  requisition_funnel_overall: FunnelGroupRow[];
  requisition_funnel_by_requisition: FunnelGroupRow[];
  requisition_funnel_by_department: FunnelGroupRow[];
  requisition_status_distribution: RequisitionStatusDistributionRow[];
  time_in_stage: Record<string, { mean_days: number; sample_size: number }>;
  interviewer_load: InterviewerLoadRow[];
  offer_acceptance_rate_overall: OfferAcceptanceRow[];
  offer_acceptance_rate_by_department: OfferAcceptanceRow[];
  offer_acceptance_rate_by_level: OfferAcceptanceRow[];
  duplicate_submission_rate_by_requisition: DuplicateSubmissionRow[];
  duplicate_submission_rate_by_department: DuplicateSubmissionRow[];
}

export interface AnomalySummary {
  checked_at: string;
  counts_by_anomaly_type: Record<string, number>;
  total_violations: number;
}
