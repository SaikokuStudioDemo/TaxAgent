/**
 * useFileUpload.ts
 * ファイルアップロード共通ロジック（領収書・請求書アップロードページで共有）
 *
 * ReceiptUploadPage.vue / ReceivedInvoiceUploadPage.vue の重複を解消する。
 */
import { ref, type Ref } from 'vue';
import { uploadFile } from '@/lib/firebase/storage';

export interface UseFileUploadOptions {
  /** Firebase Storage のベースパス（末尾に '/' を含めること。例: 'receipts/' ） */
  storagePath: string;
  /** 企業 ID の ref（アップロードパスに埋め込む） */
  corporateId: Ref<string | undefined>;
  /** 許可するファイル MIME タイプ（デフォルト: ['image/*', 'application/pdf']） */
  allowedTypes?: string[];
  /** 最大ファイルサイズ（バイト、デフォルト: 10MB） */
  maxBytes?: number;
}

export function useFileUpload(options: UseFileUploadOptions) {
  const {
    storagePath,
    corporateId,
    allowedTypes = ['image/*', 'application/pdf'],
    maxBytes = 10 * 1024 * 1024, // 10MB
  } = options;

  const fileInput = ref<HTMLInputElement | null>(null);
  const isUploading = ref(false);
  const uploadError = ref<string | null>(null);

  /** ファイルタイプの許可判定（'image/*' のようなワイルドカードに対応） */
  const isTypeAllowed = (file: File): boolean => {
    return allowedTypes.some(pattern => {
      if (pattern.endsWith('/*')) {
        return file.type.startsWith(pattern.slice(0, -1));
      }
      return file.type === pattern;
    });
  };

  /** バリデーション。問題がなければ null を返す */
  const validateFile = (file: File): string | null => {
    if (file.size > maxBytes) {
      const mb = Math.round(maxBytes / 1024 / 1024);
      return `ファイルサイズは ${mb}MB 以下にしてください`;
    }
    if (!isTypeAllowed(file)) {
      return `許可されていないファイル形式です（許可: ${allowedTypes.join(', ')}）`;
    }
    return null;
  };

  /**
   * 単一ファイルを Firebase Storage にアップロードし、ダウンロード URL を返す。
   * バリデーションエラーや例外時は null を返し、uploadError に理由をセットする。
   */
  const uploadSingleFile = async (file: File): Promise<string | null> => {
    const result = await uploadSingleFileWithPath(file);
    return result ? result.url : null;
  };

  /**
   * 単一ファイルをアップロードし、{ url, storagePath } を返す。
   * storage_path をバックエンドに保存する場合はこちらを使う。
   */
  const uploadSingleFileWithPath = async (
    file: File,
  ): Promise<{ url: string; storagePath: string } | null> => {
    const validationError = validateFile(file);
    if (validationError) {
      uploadError.value = validationError;
      return null;
    }

    isUploading.value = true;
    uploadError.value = null;
    try {
      const timestamp = Date.now();
      const corpId = corporateId.value ?? 'unknown';
      const path = `${storagePath}${corpId}/${timestamp}_${file.name}`;
      const url = await uploadFile(file, path);
      return { url, storagePath: path };
    } catch (e: any) {
      uploadError.value = e.message ?? 'ファイルのアップロードに失敗しました';
      return null;
    } finally {
      isUploading.value = false;
    }
  };

  /** ファイル選択ダイアログを開く */
  const openFilePicker = () => {
    fileInput.value?.click();
  };

  /** fileInput の value をクリアする（同じファイルを再選択できるようにする） */
  const clearFileInput = () => {
    if (fileInput.value) fileInput.value.value = '';
  };

  return {
    fileInput,
    isUploading,
    uploadError,
    openFilePicker,
    uploadSingleFile,
    uploadSingleFileWithPath,
    clearFileInput,
  };
}
