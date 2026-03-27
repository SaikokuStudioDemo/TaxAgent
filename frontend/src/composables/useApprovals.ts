import { ref } from 'vue';
import { api } from '@/lib/api';

export interface AddedStep {
  roleId: string;
  roleName: string;
  approverName?: string;
}

export interface ApprovalActionParams {
  documentType: 'receipt' | 'received_invoice' | 'issued_invoice';
  documentId: string;
  action: 'approved' | 'rejected' | 'returned';
  step: number;
  comment?: string;
  addedSteps?: AddedStep[];
}

export function useApprovals() {
  const isSubmitting = ref(false);
  const error = ref<string | null>(null);

  const submitApprovalAction = async (params: ApprovalActionParams): Promise<boolean> => {
    isSubmitting.value = true;
    error.value = null;
    try {
      // Ensure comment is null if empty string (backend requirement for some actions)
      const sanitizedComment = params.comment && params.comment.trim() !== '' ? params.comment : null;

      await api.post('/approvals/actions', {
        document_type: params.documentType,
        document_id: params.documentId,
        action: params.action,
        step: params.step,
        comment: sanitizedComment,
        added_steps: params.addedSteps || null,
      });
      return true;
    } catch (e: any) {
      error.value = e.message || '承認アクションの送信に失敗しました';
      return false;
    } finally {
      isSubmitting.value = false;
    }
  };

  return {
    isSubmitting,
    error,
    submitApprovalAction,
  };
}
