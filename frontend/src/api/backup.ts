import { apiDownload, apiUploadFile } from "./client";

export const backupApi = {
  download: () => apiDownload("/api/backup"),
  restore: (file: File) => apiUploadFile<void>("/api/backup/restore", file),
};
