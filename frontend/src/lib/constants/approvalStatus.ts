export const APPROVAL_STATUS = {
  DRAFT: 'draft',
  PENDING: 'pending_approval',
  APPROVED: 'approved',
  AUTO_APPROVED: 'auto_approved',
  REJECTED: 'rejected',
} as const

export type ApprovalStatus = typeof APPROVAL_STATUS[keyof typeof APPROVAL_STATUS]

export function isApproved(status: string): boolean {
  return (
    status === APPROVAL_STATUS.APPROVED ||
    status === APPROVAL_STATUS.AUTO_APPROVED
  )
}

export function isEditable(status: string): boolean {
  return (
    status === APPROVAL_STATUS.DRAFT ||
    status === APPROVAL_STATUS.PENDING ||
    status === APPROVAL_STATUS.REJECTED
  )
}

export function isPendingApproval(status: string): boolean {
  return status === APPROVAL_STATUS.PENDING
}
