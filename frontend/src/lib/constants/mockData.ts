/**
 * @deprecated Task#32 以降は system_settings コレクション（GET /api/v1/system-settings/plans）から取得する。
 * usePlans composable を使うこと。既存の参照箇所への影響を最小化するため削除はしない。
 */
export const PLANS = [
    {
        id: 'plan_basic',
        name: 'ベーシックプラン',
        price: 15000,
        features: ['基本機能', '月間500件までのデータ処理', 'メールサポート'],
    },
    {
        id: 'plan_standard',
        name: 'スタンダードプラン',
        price: 30000,
        features: ['全機能アクセス', '無制限のデータ処理', 'チャット・電話サポート', '優先処理'],
    },
    {
        id: 'plan_premium',
        name: 'プレミアムプラン',
        price: 50000,
        features: ['AIによる自動仕訳', '専任サポート担当', 'カスタムレポート作成', 'SLA保証'],
    }
];

/**
 * @deprecated Task#32 以降は system_settings コレクション（GET /api/v1/system-settings/options）から取得する。
 * usePlans composable を使うこと。
 */
export const OPTIONS = [
    {
        id: 'opt-data-storage',
        name: '拡張データストレージ (500GB)',
        price: 5000,
    },
    {
        id: 'opt-api-access',
        name: '外部API連携オプション',
        price: 10000,
    }
];

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
