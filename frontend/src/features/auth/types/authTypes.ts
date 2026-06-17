export type AccountRole = "Admin" | "User";

export type Account = {
  userId: string;
  workspaceId: string;
  email: string;
  displayName: string;
  role: AccountRole;
};

export type AuthSession = {
  token: string;
  expiresAt: string;
  account: Account;
};

export type AuthMode = "login" | "register";
