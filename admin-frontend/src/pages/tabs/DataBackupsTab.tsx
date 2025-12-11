import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { exportApi } from '../../api/client';

interface BackupInfo {
  name: string;
  filename: string;
  size_mb: number;
  created_at: string;
}

export function DataBackupsTab() {
  const queryClient = useQueryClient();

  const { data: backupsData, isLoading } = useQuery({
    queryKey: ['backups'],
    queryFn: () => exportApi.listBackups().then(r => r.data),
  });

  const createBackupMutation = useMutation({
    mutationFn: () => exportApi.createBackup(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backups'] });
    },
  });

  const backups: BackupInfo[] = backupsData?.backups || [];

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString();
  };

  return (
    <div className="backups-tab">
      <p className="panel-intro">
        Create and manage data backups. Backups include wiki, conversations, users, and system data.
      </p>

      <div className="backup-actions">
        <button
          className="btn-primary create-backup-btn"
          onClick={() => createBackupMutation.mutate()}
          disabled={createBackupMutation.isPending}
        >
          {createBackupMutation.isPending ? 'Creating...' : '[B] Create New Backup'}
        </button>

        {createBackupMutation.isSuccess && (
          <span className="success-message">[+] Backup created successfully</span>
        )}
      </div>

      <div className="backups-list">
        <h3>Available Backups ({backups.length})</h3>

        {isLoading ? (
          <div className="loading">Loading backups...</div>
        ) : backups.length === 0 ? (
          <div className="no-backups">
            No backups found. Create your first backup above.
          </div>
        ) : (
          <div className="backup-items">
            {backups.map((backup) => (
              <div key={backup.name} className="backup-item">
                <div className="backup-info">
                  <span className="backup-name">{backup.filename}</span>
                  <span className="backup-meta">
                    {backup.size_mb.toFixed(2)} MB | {formatDate(backup.created_at)}
                  </span>
                </div>
                <div className="backup-actions-inline">
                  <button className="btn-small" title="Download backup">
                    [v]
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="backup-schedule">
        <h3>Automatic Backups</h3>
        <p>
          Automatic daily backups run at 3:00 AM and are retained for 30 days.
          To enable automatic backups, install the systemd timer:
        </p>
        <pre className="code-block">
{`sudo cp backend/scripts/cass-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cass-backup.timer`}
        </pre>
      </div>
    </div>
  );
}
