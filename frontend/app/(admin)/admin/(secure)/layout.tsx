import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const navItems = [
  { href: "/admin/dashboard", label: "Overview" },
  { href: "/admin/economy", label: "Economy" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/promo", label: "Promo" },
  { href: "/admin/content", label: "Content" },
  { href: "/admin/system", label: "System" },
];

async function ensureSession() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const cookieHeader = cookies().toString();
  const response = await fetch(`${apiUrl}/admin/auth/session`, {
    headers: {
      cookie: cookieHeader,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    redirect("/admin/login");
  }
  return response.json();
}

export default async function SecureAdminLayout({ children }: { children: React.ReactNode }) {
  const session = await ensureSession();

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl gap-6 px-4 py-6 lg:px-6">
      <aside className="surface h-fit w-full rounded-2xl p-4 lg:sticky lg:top-6 lg:w-64">
        <p className="text-xs uppercase tracking-[0.2em] text-ember/60">Admin</p>
        <p className="mt-2 text-lg">{session.email}</p>
        <nav className="mt-4 space-y-2 text-sm">
          {navItems.map((item) => (
            <a key={item.href} href={item.href} className="block rounded-lg px-3 py-2 hover:bg-ember/5">
              {item.label}
            </a>
          ))}
        </nav>
        <form action={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/admin/auth/logout`} method="post" className="mt-6">
          <button className="w-full rounded-lg border border-ember/20 px-3 py-2 text-left text-sm">Logout</button>
        </form>
      </aside>
      <section className="flex-1">{children}</section>
    </div>
  );
}
