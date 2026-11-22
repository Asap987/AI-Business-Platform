import { redirect } from "next/navigation";

/** The root has no content of its own; the dashboard guard sends guests to /login. */
export default function RootPage() {
  redirect("/dashboard");
}
