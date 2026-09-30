import type { Metadata } from 'next';
import { headers } from 'next/headers';
import './globals.css';

export const metadata: Metadata = { title: 'LabLens · Make sense of your measurements', description: 'Check units, explore models, and understand assumptions in your school lab data. No student accounts or personal information required.', robots: { index: false, follow: false } };
export const dynamic = 'force-dynamic';
export default async function Layout({ children }: { children: React.ReactNode }) {
  await headers();
  return <html lang="en"><body><a className="skip-link" href="#main">Skip to workspace</a>{children}</body></html>;
}
