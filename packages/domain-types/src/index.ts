export type UUIDv7 = string & { readonly __uuid7: unique symbol };
export type ISODateTime = string & { readonly __isoDateTime: unique symbol };
export type TenantId = UUIDv7 & { readonly __tenantId: unique symbol };

export type ProblemDetails = {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  correlation_id: UUIDv7;
  errors?: Array<{ field: string; code: string; message: string }>;
};

export type VersionedEntity = {
  id: UUIDv7;
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
};

export const attendanceStatusCodes = [
  "present", "absent", "justified_absence", "excused_absence", "late", "late_justified",
  "early_departure", "early_departure_justified", "remote_present", "activity_present", "medical_leave",
  "institutional_leave", "attendance_pending", "not_expected", "not_enrolled", "transferred", "cancelled_session",
] as const;
export type AttendanceStatusCode = typeof attendanceStatusCodes[number];

export const teachingPlanStates = [
  "draft", "submitted_for_review", "changes_requested", "approved", "scheduled", "ready", "in_progress",
  "partially_executed", "executed", "rescheduled", "cancelled", "superseded", "archived",
] as const;
export type TeachingPlanState = typeof teachingPlanStates[number];
