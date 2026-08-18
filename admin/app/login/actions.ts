"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";

export async function login(formData: FormData): Promise<void> {
  const email = formData.get("email");
  const password = formData.get("password");
  if (typeof email !== "string" || typeof password !== "string") {
    redirect("/login?error=" + encodeURIComponent("Enter an email and password."));
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    // error.message comes from Supabase Auth, not user input echoed back —
    // safe to show directly, and never a value pricing/inventory produced
    // (CLAUDE.md rule 2 doesn't apply to auth errors).
    redirect("/login?error=" + encodeURIComponent(error.message));
  }

  redirect("/dashboard");
}
