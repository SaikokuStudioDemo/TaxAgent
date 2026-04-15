// 将来の多言語対応を見越した構造。現在は日本語固定。
export const ROLE_LABELS: Record<string, string> = {
  admin: '管理者',
  manager: 'マネージャー',
  accounting: '経理',
  staff: 'スタッフ',
  approver: '承認者',
  dept_manager: '部門長',
  group_leader: 'グループリーダー',
  tax_firm: '税理士管理者',
  corporate: '法人代表',
};

export function getRoleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}
