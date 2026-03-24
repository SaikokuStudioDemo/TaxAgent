import { getStorage, ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { app } from './config';

const storage = getStorage(app);

/**
 * Uploads a file to Firebase Storage and returns the download URL.
 * @param file The file object to upload.
 * @param path The storage path (e.g., "receipts/corp_123/image.jpg").
 * @returns Promise resolving to the download URL string.
 */
export async function uploadFile(
  file: File,
  path: string
): Promise<string> {
  const storageRef = ref(storage, path);
  await uploadBytes(storageRef, file);
  return getDownloadURL(storageRef);
}

export { storage };
