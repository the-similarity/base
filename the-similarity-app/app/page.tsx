import { DashboardShell } from "../components/dashboard-shell";
import { getDashboardData } from "../lib/api";

export default async function Page() {
  const data = await getDashboardData();

  return <DashboardShell data={data} />;
}
