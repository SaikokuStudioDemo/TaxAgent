import { z } from 'zod';

// 一般的なバリデーションルールの定義
export const contractSchema = z.object({
    loginEmail: z
        .string()
        .min(1, { message: 'メールアドレスは必須です' })
        .email({ message: '正しいメールアドレスの形式で入力してください' }),
    loginPassword: z
        .string()
        .min(8, { message: 'パスワードは8文字以上で入力してください' })
        .regex(/[a-zA-Z]/, { message: '英字を含めてください' })
        .regex(/[0-9]/, { message: '数字を含めてください' }),
    companyName: z
        .string()
        .min(1, { message: '法人名は必須です' })
        .max(100, { message: '法人名は100文字以内で入力してください' }),
    companyUrl: z
        .string()
        .url({ message: '正しいURLの形式で入力してください' })
        .optional()
        .or(z.literal('')), // 任意項目なので空文字も許容
    address: z
        .string()
        .min(1, { message: '所在地は必須です' })
        .max(200, { message: '所在地は200文字以内で入力してください' }),
    maIntent: z
        .enum(['none', 'considering', 'immediate'])
        .optional()
        .or(z.literal('')), // 税理士法人のみ使用・任意で未選択(空)も許容
});

export type ContractFormValues = z.infer<typeof contractSchema>;
