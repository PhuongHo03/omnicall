import { RefreshCcw, ShieldCheck, Trash2, UsersRound } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "../../../shared/components/ConfirmDialog";
import type { AdminAccount, AdminAccountRole } from "../types/adminTypes";

type AdminAccountsTableProps = {
  accounts: AdminAccount[];
  deletingAccountId: string | null;
  isLoading: boolean;
  updatingAccountId: string | null;
  onDeleteAccount: (userId: string) => void;
  onRefresh: () => void;
  onRoleChange: (userId: string, role: AdminAccountRole) => void;
};

export function AdminAccountsTable({
  accounts,
  deletingAccountId,
  isLoading,
  onDeleteAccount,
  onRefresh,
  onRoleChange,
  updatingAccountId
}: AdminAccountsTableProps) {
  const [accountIdToDelete, setAccountIdToDelete] = useState<string | null>(null);
  const accountToDelete = accounts.find((account) => account.userId === accountIdToDelete) ?? null;

  return (
    <section className="admin-panel">
      <div className="panel-heading admin-panel-heading-actions">
        <div>
          <h2>Accounts</h2>
          <span>Manage local account roles.</span>
        </div>
        <button className="icon-button icon-button--secondary" disabled={isLoading} type="button" onClick={onRefresh}>
          <RefreshCcw size={16} />
          Refresh
        </button>
      </div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Account</th>
              <th>Created</th>
              <th>Role</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((account) => (
              <tr key={account.userId}>
                <td>
                  <div className="account-cell">
                    <UsersRound size={16} />
                    <div>
                      <strong>{account.displayName}</strong>
                      <span>{account.email}</span>
                    </div>
                  </div>
                </td>
                <td>{new Date(account.createdAt).toLocaleString()}</td>
                <td>
                  <div className="role-control">
                    <ShieldCheck size={16} />
                    <select
                      value={account.role}
                      disabled={!account.canChangeRole || updatingAccountId === account.userId}
                      title={account.canChangeRole ? "Change account role" : "You cannot change your own role"}
                      onChange={(event) => onRoleChange(account.userId, event.target.value as AdminAccountRole)}
                    >
                      <option value="Admin">Admin</option>
                      <option value="User">User</option>
                    </select>
                  </div>
                </td>
                <td>
                  <button
                    className="icon-only-button icon-only-button--danger"
                    type="button"
                    disabled={!account.canChangeRole || deletingAccountId === account.userId}
                    title={account.canChangeRole ? "Delete account" : "You cannot delete your own account"}
                    onClick={() => setAccountIdToDelete(account.userId)}
                  >
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            ))}
            {accounts.length === 0 ? (
              <tr>
                <td colSpan={5}>No accounts reported.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <ConfirmDialog
        isOpen={Boolean(accountToDelete)}
        title="Delete account"
        message={
          accountToDelete
            ? `Delete account ${accountToDelete.email}? This will delete its meetings, chat sessions, and stored files.`
            : ""
        }
        confirmLabel="Delete account"
        onCancel={() => setAccountIdToDelete(null)}
        onConfirm={() => {
          if (accountToDelete) {
            onDeleteAccount(accountToDelete.userId);
          }
          setAccountIdToDelete(null);
        }}
      />
    </section>
  );
}
