/**
 * approvalTypes.ts - 承認関連の共通型定義
 *
 * 領収書・請求書の承認ダッシュボード、詳細モーダルなどで
 * 共通利用する型をここに集約し、各ファイルでの重複定義を排除する。
 */

// ─── 承認ステップ履歴 ───
export interface ApprovalHistory {
  id?: string;
  step: number;
  roleId: string;
  roleName: string;
  approverId?: string;
  approverName?: string;
  status: 'pending' | 'approved' | 'rejected' | 'skipped';
  actionDate?: string;
  comment?: string;
}

