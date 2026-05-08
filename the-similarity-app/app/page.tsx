import { redirect } from "next/navigation";

/**
 * Product entrypoint.
 *
 * The sellable setup scanner owns localhost:3000 during product development.
 * Marketing copy now belongs in the separate landing deploy target; keeping
 * this route as a server redirect prevents the app shell from silently
 * becoming a mixed marketing/lab surface again.
 */
export default function HomePage() {
  redirect("/scanner");
}
