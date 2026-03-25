/**
 * useApprovalHistory.ts
 * 承認ステップ表示ロジックの共通ユーティリティ
 * InvoiceListPage / InvoiceApprovalPage / ApprovalDashboardPage で共有
 */

export interface ApprovalHistory {
  id: string;
  step: number;
  roleId: string;
  roleName: string;
  approverId?: string;
  approverName?: string;
  status: 'pending' | 'approved' | 'rejected' | 'skipped';
  actionDate?: string;
  comment?: string;
}

export const roleLabel: Record<string, string> = {
  accounting:     '経理担当',
  direct_manager: '直属上長',
  dept_manager:   '部門長',
  admin:          '管理者',
  group_leader:   'グループリーダー',
};

/**
 * ドキュメント（請求書・領収書）の承認ステップ表示用履歴を構築する。
 *
 * @param approvalSteps  - DBの approval_steps（ルール定義ステップ配列）
 * @param approvalEvents - DBの approval_history（完了済みイベント配列）
 * @param approvalStatus - DBの approval_status（'approved' | 'rejected' | 'pending_approval'）
 */
export function buildApprovalHistory(
  approvalSteps: any[],
  approvalEvents: any[],
  reviewStatus?: string,
): ApprovalHistory[] {
  // 完了済みイベントをステップ番号でインデックス化
  const events: Record<number, any> = {};
  for (const h of approvalEvents ?? []) {
    const s = h.step ?? 1;
    events[s] = h;
  }

  // approval_steps があればそれを正とする
  if (approvalSteps && approvalSteps.length > 0) {
    return approvalSteps.map((s: any) => {
      const event = events[s.step];
      return {
        id: event?.id ?? `step_${s.step}`,
        step: s.step,
        roleId: s.role,
        roleName: roleLabel[s.role] ?? s.role,
        approverId: event?.approver_id,
        approverName: event?.approver_name,
        status: event
          ? (event.action === 'approved' ? 'approved' : event.action === 'rejected' ? 'rejected' : 'pending')
          : 'pending',
        actionDate: event?.action_date ?? event?.timestamp,
        comment: event?.comment,
      };
    });
  }

  // approval_steps がない場合はイベント履歴から構築
  const historyArr = Object.values(events);
  if (historyArr.length > 0) {
    return historyArr.map((h: any, i: number) => ({
      id: h.id ?? `h_${i}`,
      step: h.step ?? i + 1,
      roleId: h.role_id ?? 'accounting',
      roleName: h.role_name ?? roleLabel[h.role_id] ?? '経理担当',
      approverId: h.approver_id,
      approverName: h.approver_name,
      status: (h.action === 'approved' ? 'approved' : h.action === 'rejected' ? 'rejected' : 'pending') as any,
      actionDate: h.action_date ?? h.timestamp,
      comment: h.comment,
    }));
  }

  // どちらもない場合のデフォルト（1ステップ）
  const fallbackStatus = reviewStatus === 'approved' ? 'approved' : reviewStatus === 'rejected' ? 'rejected' : 'pending';
  return [{ id: 'h_default', step: 1, roleId: 'accounting', roleName: '承認担当', status: fallbackStatus as any }];
}
