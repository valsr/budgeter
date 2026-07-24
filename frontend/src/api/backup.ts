import { apiDownload, apiUpload } from "./client";

export const backupApi = {
  download: () => apiDownload("/api/backup"),
  restore: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<void>("/api/backup/restore", form);
  },
};
