import { useCallback, useEffect, useState } from "react";

import { deleteAdminAccount, getAdminAccounts, updateAdminAccountRole } from "../api/adminApi";
import type { AdminAccount, AdminAccountRole } from "../types/adminTypes";

export function useAdminAccounts(token: string) {
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [deletingAccountId, setDeletingAccountId] = useState<string | null>(null);
  const [updatingAccountId, setUpdatingAccountId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshAccounts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getAdminAccounts(token);
      setAccounts(response.items);
      setNotice("Accounts refreshed.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Accounts request failed.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refreshAccounts();
  }, [refreshAccounts]);

  const updateAccountRole = useCallback(
    async (userId: string, role: AdminAccountRole) => {
      setUpdatingAccountId(userId);
      setError(null);
      try {
        const updatedAccount = await updateAdminAccountRole(token, userId, role);
        setAccounts((current) => current.map((account) => (account.userId === userId ? updatedAccount : account)));
        setNotice(`Updated ${updatedAccount.email} to ${updatedAccount.role}.`);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Role update failed.");
      } finally {
        setUpdatingAccountId(null);
      }
    },
    [token]
  );

  const deleteAccount = useCallback(
    async (userId: string) => {
      setDeletingAccountId(userId);
      setError(null);
      try {
        await deleteAdminAccount(token, userId);
        setAccounts((current) => current.filter((account) => account.userId !== userId));
        setNotice("Account deleted.");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Account delete failed.");
      } finally {
        setDeletingAccountId(null);
      }
    },
    [token]
  );

  return {
    accounts,
    deleteAccount,
    deletingAccountId,
    error,
    isLoading,
    notice,
    refreshAccounts,
    updateAccountRole,
    updatingAccountId
  };
}
