import { login } from "./actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return (
    <main>
      <h1>تسجيل الدخول</h1>
      {error && <p role="alert">{error}</p>}
      <form>
        <div>
          <label htmlFor="email">البريد الإلكتروني</label>
          <input id="email" name="email" type="email" required autoComplete="email" />
        </div>
        <div>
          <label htmlFor="password">كلمة المرور</label>
          <input
            id="password"
            name="password"
            type="password"
            required
            autoComplete="current-password"
          />
        </div>
        <button formAction={login} type="submit">
          دخول
        </button>
      </form>
    </main>
  );
}
