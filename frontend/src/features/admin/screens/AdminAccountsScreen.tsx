import { AdminNavbar } from "../components/AdminNavbar";
import { PageHeader } from "../../../shared/components/PageHeader";
import { AdminAccountsTable } from "../components/AdminAccountsTable";
import { useAdminAccounts } from "../hooks/useAdminAccounts";

type AdminAccountsScreenProps = {
  token: string;
};

export function AdminAccountsScreen({ token }: AdminAccountsScreenProps) {
  const accounts = useAdminAccounts(token);

  return (
    <div className="admin-screen">
      <AdminNavbar />
      <PageHeader title="Account Management" subtitle="Manage local Omnicall accounts and product roles." />

      <AdminAccountsTable
        accounts={accounts.accounts}
        deletingAccountId={accounts.deletingAccountId}
        isLoading={accounts.isLoading}
        updatingAccountId={accounts.updatingAccountId}
        onDeleteAccount={(userId) => void accounts.deleteAccount(userId)}
        onRefresh={() => void accounts.refreshAccounts(true)}
        onRoleChange={(userId, role) => void accounts.updateAccountRole(userId, role)}
      />

    </div>
  );
}
