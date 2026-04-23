export const APPROVAL_LEVELS = [
    { value: 'staff', label: '一般担当者' },
    { value: 'group_leader', label: '係長 / グループリーダー' },
    { value: 'manager', label: '部長 / マネージャー' },
    { value: 'director', label: '役員' },
    { value: 'president', label: '社長 / 代表取締役' },
];

export const INITIAL_USERS = [
    {
        id: 'user-1',
        name: '山田 太郎',
        email: 'yamada@example.com',
        role: 'president',
        permissions: {
            dataProcessing: true,
            reportExtraction: true,
        }
    },
];




/**
 * roleIdからランク（承認階層の高さ）を判定するユーティリティ
 * 個別承認者追加時に「現在の承認者より上位のみ選択可能」とするために使用
 */
export const getRankFromRoleId = (roleId: string): number => {
  if (roleId.includes('staff')) return 1;
  if (roleId.includes('accounting')) return 2;
  if (roleId.includes('leader')) return 2;
  if (roleId.includes('manager')) return 3;
  if (roleId.includes('director')) return 4;
  if (roleId.includes('president')) return 5;
  return 1;
};
