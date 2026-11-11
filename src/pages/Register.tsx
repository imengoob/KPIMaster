import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getApiErrorMessage, getDefaultHomePath, useAuth } from "@/contexts/AuthContext";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const Register = () => {
  const { isAuthenticated, isAuthLoading, register, user } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [accountType, setAccountType] = useState<"company_admin" | "developer">("company_admin");
  const [companyName, setCompanyName] = useState("");
  const [companySlug, setCompanySlug] = useState("");
  const [companyType, setCompanyType] = useState<"client" | "vendor">("client");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isAuthLoading && isAuthenticated) {
    return <Navigate to={getDefaultHomePath(user)} replace />;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (accountType === "developer" && !companySlug.trim()) {
      setError("Company slug is required for developer accounts.");
      return;
    }

    setIsSubmitting(true);
    try {
      await register({
        username,
        email,
        password,
        account_type: accountType === "company_admin" && companyType === "vendor" ? "esn_admin" : accountType,
        company_name: companyName || undefined,
        company_slug: companySlug || undefined,
        company_type: companyType,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-sm space-y-6">
        {/* Brand */}
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            KPIMaster · Norma Tunisie
          </p>
          <h1 className="text-2xl font-bold text-foreground">Create account</h1>
          <p className="text-sm text-muted-foreground">
            Register a new account to access dashboards and live Trello data.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="account-type">Account type</Label>
            <Select
              value={accountType}
              onValueChange={(value: "company_admin" | "developer") => setAccountType(value)}
            >
              <SelectTrigger id="account-type">
                <SelectValue placeholder="Choose an account type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="company_admin">Company account</SelectItem>
                <SelectItem value="developer">Developer account</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {accountType === "company_admin" && (
            <div className="space-y-2">
              <Label htmlFor="company-type">Company Type</Label>
              <Select
                value={companyType}
                onValueChange={(value: "client" | "vendor") => setCompanyType(value)}
                name="company_type"
              >
                <SelectTrigger id="company-type">
                  <SelectValue placeholder="Are you a Client or a Vendor?" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="client">Client Company</SelectItem>
                  <SelectItem value="vendor">Outsourcing / Vendor Partner</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {accountType === "company_admin" ? (
            <div className="space-y-2">
              <Label htmlFor="company-name">Company name</Label>
              <Input
                id="company-name"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Optional. Defaults to your workspace name"
              />
            </div>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="company-slug">Target Company slug</Label>
              <Input
                id="company-slug"
                value={companySlug}
                onChange={(e) => setCompanySlug(e.target.value)}
                placeholder="your-company-slug"
                required
              />
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="your-username"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              placeholder="you@example.com"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              placeholder="••••••••"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirm-password">Confirm password</Label>
            <Input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              placeholder="••••••••"
              required
            />
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/login" className="text-primary underline underline-offset-2">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
};

export default Register;
