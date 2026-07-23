import { useCallback, useEffect, useState } from "react";

import { deleteAdminAccount, getAdminAccounts, updateAdminAccountRole } from "../api/adminApi";
import type { AdminAccount, AdminAccountRole } from "../types/adminTypes";
import { useToast } from "../../../shared/layouts/ToastContext";

export function useAdminAccounts(token: string) {
  const { showToast } = useToast();
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [deletingAccountId, setDeletingAccountId] = useState<string | null>(null);
  const [updatingAccountId, setUpdatingAccountId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshAccounts = useCallback(async (announce = false) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getAdminAccounts(token);
      setAccounts(response.items);
      setNotice("Accounts refreshed.");
      if (announce) showToast({ message: "Accounts refreshed.", tone: "success" });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Accounts request failed.";
      setError(message);
      if (announce) showToast({ message, tone: "error" });
    } finally {
      setIsLoading(false);
    }
  }, [showToast, token]);

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
