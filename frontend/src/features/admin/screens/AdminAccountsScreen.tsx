import { AdminAccountsTable } from "../components/AdminAccountsTable";
import { useAdminAccounts } from "../hooks/useAdminAccounts";

type AdminAccountsScreenProps = {
  token: string;
};

export function AdminAccountsScreen({ token }: AdminAccountsScreenProps) {
  const accounts = useAdminAccounts(token);

  return (
    <div className="admin-screen">
      <section className="admin-hero">
        <div>
          <h1>Account Management</h1>
          <span>Manage local Omnicall accounts and product roles.</span>
        </div>
      </section>

      <AdminAccountsTable
        accounts={accounts.accounts}
        deletingAccountId={accounts.deletingAccountId}
        isLoading={accounts.isLoading}
        updatingAccountId={accounts.updatingAccountId}
        onDeleteAccount={(userId) => void accounts.deleteAccount(userId)}
        onRefresh={() => void accounts.refreshAccounts()}
        onRoleChange={(userId, role) => void accounts.updateAccountRole(userId, role)}
      />

      <div className="event-strip" aria-live="polite">
        <span className={accounts.error ? "event-strip__error" : ""}>
          {accounts.error ?? accounts.notice ?? "Ready"}
        </span>
      </div>
    </div>
  );
}
